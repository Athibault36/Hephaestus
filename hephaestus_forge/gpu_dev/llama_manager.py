"""Manage llama.cpp OpenAI-compatible server for GPU inference."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_MODEL_REPO = "bartowski/Qwen2.5-Coder-7B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"


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

    def ensure_server_deps(self, prefer_gpu: bool = True) -> None:
        try:
            import llama_cpp  # noqa: F401
            return
        except ImportError:
            pass

        import platform
        pip_cmd = [sys.executable, "-m", "pip", "install", "-q", "--force-reinstall"]
        if prefer_gpu and platform.system() == "Linux" and shutil.which("nvidia-smi"):
            try:
                subprocess.check_call(
                    pip_cmd + [
                        "llama-cpp-python",
                        "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124",
                    ],
                )
                subprocess.call(pip_cmd[:4] + ["nvidia-cuda-runtime-cu12", "nvidia-cublas-cu12"])
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
        ]
        try:
            import nvidia.cuda_runtime.lib as cuda_rt  # type: ignore[import-untyped]
            paths.insert(0, str(Path(cuda_rt.__file__).parent))
        except Exception:
            pass
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join([p for p in paths if Path(p).exists()] + ([existing] if existing else []))
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

        ngl = self.n_gpu_layers
        for attempt in ("gpu", "cpu"):
            if attempt == "cpu":
                ngl = 0

            cmd = [
                sys.executable, "-m", "llama_cpp.server",
                "--model", str(model),
                "--host", self.host,
                "--port", str(self.port),
                "--n_gpu_layers", str(ngl),
                "--n_ctx", str(self.ctx_size),
            ]
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
