"""Manage a llama.cpp OpenAI-compatible server for GPU inference.

Tuned for coding models on datacenter Ada GPUs (notably the NVIDIA L40S, 48 GB),
while degrading gracefully to smaller GPUs and CPU. The argv/settings logic is
factored into pure functions so it can be unit tested without a GPU.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import httpx

DEFAULT_MODEL_REPO = "bartowski/Qwen2.5-Coder-7B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"

# GPU families that support llama.cpp flash-attention well (Ampere and newer).
_FLASH_ATTN_GPUS = re.compile(
    r"(L40S?|L4|A100|A6000|A40|H100|H200|RTX\s?(?:30|40|50)\d0|RTX\s?A\d+)",
    re.IGNORECASE,
)


@dataclass
class GPUSettings:
    """Resolved llama.cpp server tuning parameters."""

    n_gpu_layers: int
    n_ctx: int
    n_batch: int
    flash_attn: bool
    n_threads: int
    cont_batching: bool = True

    def describe(self) -> str:
        placement = "all-GPU" if self.n_gpu_layers < 0 else f"{self.n_gpu_layers} GPU layers"
        fa = "flash-attn" if self.flash_attn else "no-flash-attn"
        return f"{placement}, ctx={self.n_ctx}, batch={self.n_batch}, {fa}"


def recommend_gpu_settings(
    gpu_name: Optional[str],
    vram_free_mb: int,
    requested_ctx: int = 32768,
    requested_gpu_layers: int = -1,
) -> GPUSettings:
    """Pick sane, fast defaults for a coding model given the detected GPU.

    - No GPU / no VRAM -> CPU only (no offload, no flash-attention).
    - >= ~40 GB (L40S/A100/H100) -> full offload, large batch, big context.
    - Ampere/Ada/Hopper -> enable flash-attention.
    """
    cpu_threads = max(4, (os.cpu_count() or 8))

    if not gpu_name or vram_free_mb <= 0:
        # CPU fallback: keep context modest and disable GPU-only features.
        return GPUSettings(
            n_gpu_layers=0,
            n_ctx=min(requested_ctx, 8192),
            n_batch=256,
            flash_attn=False,
            n_threads=cpu_threads,
            cont_batching=True,
        )

    flash_attn = bool(_FLASH_ATTN_GPUS.search(gpu_name))

    if vram_free_mb >= 40000:  # L40S (48 GB), A100, H100
        n_ctx = requested_ctx
        n_batch = 512
        n_gpu_layers = requested_gpu_layers  # typically -1 (all)
    elif vram_free_mb >= 20000:  # 24 GB class (RTX 4090, A5000)
        n_ctx = min(requested_ctx, 16384)
        n_batch = 512
        n_gpu_layers = requested_gpu_layers
    elif vram_free_mb >= 10000:  # ~12-16 GB
        n_ctx = min(requested_ctx, 8192)
        n_batch = 256
        n_gpu_layers = requested_gpu_layers
    else:  # small GPU: partial offload
        n_ctx = min(requested_ctx, 4096)
        n_batch = 128
        n_gpu_layers = requested_gpu_layers if requested_gpu_layers >= 0 else 20

    return GPUSettings(
        n_gpu_layers=n_gpu_layers,
        n_ctx=n_ctx,
        n_batch=n_batch,
        flash_attn=flash_attn,
        n_threads=cpu_threads,
        cont_batching=True,
    )


def build_llama_server_argv(
    python_exe: str,
    model: Path,
    host: str,
    port: int,
    settings: GPUSettings,
) -> List[str]:
    """Construct the ``python -m llama_cpp.server`` argv from resolved settings."""
    argv = [
        python_exe, "-m", "llama_cpp.server",
        "--model", str(model),
        "--host", host,
        "--port", str(port),
        "--n_gpu_layers", str(settings.n_gpu_layers),
        "--n_ctx", str(settings.n_ctx),
        "--n_batch", str(settings.n_batch),
        "--n_threads", str(settings.n_threads),
    ]
    if settings.flash_attn:
        argv += ["--flash_attn", "true"]
    if settings.cont_batching:
        argv += ["--cont_batching", "true"]
    return argv


def detect_primary_gpu() -> Optional[Tuple[str, int, int]]:
    """Return (name, vram_total_mb, vram_free_mb) for GPU 0, or None if absent."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    first = out.splitlines()[0] if out else ""
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 3:
        return None
    try:
        return parts[0], int(float(parts[1])), int(float(parts[2]))
    except ValueError:
        return None


class LlamaServerManager:
    def __init__(
        self,
        models_dir: Path,
        host: str = "0.0.0.0",
        port: int = 8080,
        n_gpu_layers: int = -1,
        ctx_size: int = 32768,
    ):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.host = host
        self.port = port
        self.n_gpu_layers = n_gpu_layers
        self.ctx_size = ctx_size
        self._proc: Optional[subprocess.Popen] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def default_model_path(self, filename: str = DEFAULT_MODEL_FILE) -> Path:
        return self.models_dir / filename

    def resolve_settings(self) -> GPUSettings:
        """Resolve tuning parameters from the detected GPU (or CPU fallback)."""
        gpu = detect_primary_gpu()
        if gpu:
            name, _total, free = gpu
            return recommend_gpu_settings(name, free, self.ctx_size, self.n_gpu_layers)
        return recommend_gpu_settings(None, 0, self.ctx_size, self.n_gpu_layers)

    def ensure_model(
        self,
        repo_id: str = DEFAULT_MODEL_REPO,
        filename: str = DEFAULT_MODEL_FILE,
    ) -> Path:
        dest = self.default_model_path(filename)
        if dest.exists() and dest.stat().st_size > 1_000_000:
            return dest

        try:
            from huggingface_hub import hf_hub_download
        except ImportError as e:
            raise RuntimeError("Install huggingface_hub: pip install huggingface_hub") from e

        downloaded = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=str(self.models_dir),
        )
        return Path(downloaded)

    @staticmethod
    def _cuda_wheel_index() -> Optional[str]:
        """Pick a llama-cpp-python CUDA wheel index from the driver's CUDA version."""
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                text=True, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        # Prebuilt wheels exist for cu121..cu125; L40S drivers ship CUDA 12.4+.
        # Use cu124 which is broadly compatible with the 12.x runtime.
        return "https://abetlen.github.io/llama-cpp-python/whl/cu124"

    def ensure_server_deps(self, prefer_gpu: bool = True) -> None:
        try:
            import llama_cpp  # noqa: F401
            return
        except ImportError:
            pass

        pip_cmd = [sys.executable, "-m", "pip", "install", "-q"]
        if prefer_gpu and platform.system() == "Linux" and shutil.which("nvidia-smi"):
            wheel_index = self._cuda_wheel_index()
            if wheel_index:
                try:
                    subprocess.check_call(
                        pip_cmd + ["llama-cpp-python", "--extra-index-url", wheel_index]
                    )
                    return
                except subprocess.CalledProcessError:
                    pass
        subprocess.check_call(pip_cmd + ["llama-cpp-python"])

    @staticmethod
    def _cuda_env() -> dict[str, str]:
        env = os.environ.copy()
        paths = [
            "/usr/local/cuda/lib64",
            "/usr/local/cuda-13.0/targets/x86_64-linux/lib",
            "/usr/local/cuda-12.4/targets/x86_64-linux/lib",
        ]
        try:
            import nvidia.cuda_runtime.lib as cuda_rt  # type: ignore[import-untyped]
            paths.insert(0, str(Path(cuda_rt.__file__).parent))
        except Exception:
            pass
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(
            [p for p in paths if Path(p).exists()] + ([existing] if existing else [])
        )
        return env

    def is_healthy(self, timeout: float = 2.0) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def start(
        self,
        model_path: Optional[Path] = None,
        wait_seconds: int = 300,
    ) -> subprocess.Popen:
        if self.is_healthy():
            return self._proc  # type: ignore[return-value]

        self.ensure_server_deps()
        model = model_path or self.default_model_path()
        if not model.exists():
            raise FileNotFoundError(f"Model not found: {model}. Run with --download first.")

        settings = self.resolve_settings()
        for attempt in ("gpu", "cpu"):
            if attempt == "cpu":
                settings = recommend_gpu_settings(None, 0, self.ctx_size, 0)

            cmd = build_llama_server_argv(sys.executable, model, self.host, self.port, settings)
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=self._cuda_env(),
            )
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if self.is_healthy():
                    return self._proc
                if self._proc.poll() is not None:
                    out = self._proc.stdout.read() if self._proc.stdout else ""
                    if attempt == "gpu" and "libcud" in out.lower():
                        break
                    raise RuntimeError(f"llama server exited early:\n{out}")
                time.sleep(2)
            if attempt == "gpu":
                self._proc = None
                continue
            raise TimeoutError(f"llama server did not become healthy within {wait_seconds}s")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    @staticmethod
    def nvidia_smi_summary() -> str:
        if not shutil.which("nvidia-smi"):
            return "nvidia-smi not available"
        try:
            return subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader"],
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            return "nvidia-smi query failed"
