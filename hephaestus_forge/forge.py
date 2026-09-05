#!/usr/bin/env python3
"""
HephaestusForge — Local-First Agent Factory for UE5.8 Autonomous Agents

CLI Entry Point: init, compile, deploy, observe, evolve
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

# Load factory-root .env early so NVIDIA_API_KEY / HEPHAESTUS_* persist across forge cmds.
def _load_factory_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    factory_root = Path(__file__).resolve().parent.parent
    env_path = factory_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


_load_factory_dotenv()

import typer
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.tree import Tree
import yaml

# Cloud imports (optional - only used if cloud features enabled)
try:
    try:
        from hephaestus_forge.cloud.budget_manager import BudgetManager, BudgetExceededError
        from hephaestus_forge.cloud.nim_client import NIMClient
        from hephaestus_forge.cloud.bitdeer_client import BitdeerClient
        from hephaestus_forge.cloud.brev_client import BrevClient
    except ImportError:
        from cloud.budget_manager import BudgetManager, BudgetExceededError
        from cloud.nim_client import NIMClient
        from cloud.bitdeer_client import BitdeerClient
        from cloud.brev_client import BrevClient
    CLOUD_AVAILABLE = True
except ImportError:
    CLOUD_AVAILABLE = False
    BudgetManager = None
    BudgetExceededError = Exception
    NIMClient = None
    BitdeerClient = None
    BrevClient = None

# ──────────────────────────────────────────────────────────────────────────────
# Configuration Models (Pydantic Settings)
# ──────────────────────────────────────────────────────────────────────────────

class GPUInfo(BaseModel):
    index: int
    name: str
    vram_total_mb: int
    vram_free_mb: int
    driver_version: str
    cuda_version: str


class SystemScanResult(BaseModel):
    platform: str
    python_version: str
    python_executable: str
    ue_path: Optional[str] = None
    ue_version: Optional[str] = None
    blender_path: Optional[str] = None
    blender_version: Optional[str] = None
    cc5_path: Optional[str] = None
    gpus: list[GPUInfo] = Field(default_factory=list)
    total_vram_mb: int = 0
    recommended_quant: str = "Q4_K_M"
    vision_resolution: int = 512
    tts_model_size: str = "small"
    warnings: list[str] = Field(default_factory=list)


class ModelConfig(BaseModel):
    planner: dict = Field(default_factory=lambda: {
        "model_id": "nvidia/nemotron-3-ultra-550b-a55b",
        "base_url": "https://integrate.api.nvidia.com/v1",
    })
    nemotron: dict = Field(default_factory=lambda: {
        "model_id": "nvidia/nemotron-3-ultra-550b-a55b",
        "quantization": "Q4_K_M",
        "context_length": 131072,
        "rope_scaling": {"type": "linear", "factor": 2.0},
        "gpu_layers": -1,
        "tensor_split": None,
    })
    whisper: dict = Field(default_factory=lambda: {
        "model": "large-v3",
        "device": "cuda",
        "compute_type": "float16",
        "language": "en",
    })
    tts: dict = Field(default_factory=lambda: {
        "primary": "fish-speech",
        "fallback": "xtts",
        "voice_cloning": {
            "enabled": True,
            "reference_audio_dir": "ProjectMemory/voice_library/references",
            "embedding_cache_dir": "ProjectMemory/voice_library/embeddings",
            "default_voice": "hephaestus_default",
        },
        "models": {
            "fish_speech": {"model_path": "models/fish-speech-1.5-q4_k_m.gguf", "compile": True},
            "xtts": {"model_path": "models/xtts_v2.onnx"},
            "openvoice": {"model_path": "models/openvoice_v2.onnx"},
        },
    })
    vision: dict = Field(default_factory=lambda: {
        "detection": "yolo-world",
        "segmentation": "sam2",
        "classification": "clip",
        "captioning": "florence-2",
        "resolution": 512,
        "fps": 15,
        "gbuffer_capture": True,
    })
    inference: dict = Field(default_factory=lambda: {
        "backend": "tensorrt-llm",
        "fallback_backend": "llama.cpp",
        "host": "127.0.0.1",
        "port": 8080,
        "sampling": {
            "temperature": 0.3,
            "top_p": 0.95,
            "min_p": 0.05,
            "repeat_penalty": 1.05,
        },
    })


class NetworkConfig(BaseModel):
    grpc_port: int = 50051
    webrtc_port: int = 8081
    dashboard_port: int = 3000
    tts_port: int = 8082
    vision_port: int = 8083
    dcc_bridge_port: int = 8084
    remote_api_port: int = 8765
    allowed_external: list[str] = Field(default_factory=lambda: ["api.meshy.ai"])


class PathsConfig(BaseModel):
    project_root: str
    forge_dir: str = ".hephaestus_forge"
    ue_plugin_dir: str = "UE5_Plugin_Source/HephaestusBridge"
    agent_runtime_dir: str = "Agent_Runtime"
    memory_dir: str = "ProjectMemory"
    mission_control_dir: str = "MissionControl"


class CloudConfig(BaseModel):
    budget: dict = Field(default_factory=lambda: {
        "monthly_limit_usd": 25,
        "per_session_limit_usd": 25,
        "hard_ceiling_usd": 25,
        "alert_threshold_pct": 80,
        "auto_stop_at_limit": True,
        "stop_at_budget_fraction": 0.92,
    })
    providers: list[dict] = Field(default_factory=list)
    routing: dict = Field(default_factory=lambda: {"rules": []})
    session: dict = Field(default_factory=lambda: {
        "idle_timeout_minutes": 15,
        "max_duration_hours": 10,
        "checkpoint_interval_minutes": 30,
        "persist_volumes": True,
        "force_stop_on_exit": True,
    })


class ForgeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HEPHAESTUS_",
        case_sensitive=False,
        extra="allow",
    )

    project_name: str = "HephaestusProject"
    system: SystemScanResult
    models: ModelConfig = Field(default_factory=ModelConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    paths: PathsConfig
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    agent_runtime: dict = Field(default_factory=dict)
    mission_control: dict = Field(default_factory=dict)
    security: dict = Field(default_factory=dict)
    observability: dict = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "ForgeConfig":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_scan(cls, project_name: str, project_root: Path, scan: SystemScanResult) -> "ForgeConfig":
        paths = PathsConfig(project_root=str(project_root))
        # Load cloud config from template if exists
        cloud_config = CloudConfig()
        return cls(project_name=project_name, system=scan, paths=paths, cloud=cloud_config)


# ──────────────────────────────────────────────────────────────────────────────
# System Scanner
# ──────────────────────────────────────────────────────────────────────────────

class SystemScanner:
    def __init__(self, console: Console):
        self.console = console

    def scan(self) -> SystemScanResult:
        self.console.print("[bold cyan]Scanning system...[/bold cyan]")

        result = SystemScanResult(
            platform=platform.platform(),
            python_version=platform.python_version(),
            python_executable=sys.executable,
        )


        # GPU Detection
        result.gpus = self._scan_gpus()
        result.total_vram_mb = sum(g.vram_total_mb for g in result.gpus)
        self._configure_vram_budget(result)

        # UE5.8 Detection
        result.ue_path, result.ue_version = self._find_ue58()
        if not result.ue_path:
            result.warnings.append("UE5.8 not found. Set UE_PATH env var or install at ~/UnrealEngine/5.8")

        # Blender Detection
        result.blender_path, result.blender_version = self._find_blender()
        if not result.blender_path:
            result.warnings.append("Blender not found. Install Blender 4.x for DCC integration.")

        # CC5 Detection
        result.cc5_path = self._find_cc5()
        if not result.cc5_path:
            result.warnings.append("Character Creator 5 not found. Optional for character pipeline.")

        self._print_scan_summary(result)
        return result

    def _scan_gpus(self) -> list[GPUInfo]:
        gpus = []
        try:
            # nvidia-smi query
            cmd = [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            for line in output.splitlines():
                idx, name, mem_total, mem_free, driver = [x.strip() for x in line.split(",")]
                gpus.append(GPUInfo(
                    index=int(idx),
                    name=name,
                    vram_total_mb=int(mem_total),
                    vram_free_mb=int(mem_free),
                    driver_version=driver,
                    cuda_version=self._get_cuda_version(),
                ))
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.console.print("[yellow][WARN] nvidia-smi not found. GPU acceleration unavailable.[/yellow]")

        return gpus

    def _get_cuda_version(self) -> str:
        try:
            output = subprocess.check_output(["nvcc", "--version"], text=True, stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                if "release" in line.lower():
                    return line.split("release")[-1].split(",")[0].strip()
        except Exception:
            pass
        return "unknown"

    def _configure_vram_budget(self, result: SystemScanResult) -> None:
        total_vram = result.total_vram_mb
        if total_vram >= 48000:  # 48GB+
            result.recommended_quant = "Q8_0"
            result.vision_resolution = 1024
            result.tts_model_size = "large"
        elif total_vram >= 24000:  # 24GB+
            result.recommended_quant = "Q4_K_M"
            result.vision_resolution = 768
            result.tts_model_size = "medium"
        elif total_vram >= 16000:  # 16GB+
            result.recommended_quant = "Q4_K_M"
            result.vision_resolution = 512
            result.tts_model_size = "small"
            result.warnings.append("VRAM < 24GB: CPU offload recommended for Nemotron")
        elif total_vram > 0:
            result.recommended_quant = "Q3_K_M"
            result.vision_resolution = 512
            result.tts_model_size = "small"
            result.warnings.append(f"VRAM ({total_vram}MB) < 16GB: Heavy CPU offload required")
        else:
            result.warnings.append("No GPU detected: CPU-only mode (very slow)")

    def _find_ue58(self) -> tuple[Optional[str], Optional[str]]:
        def _version_from(path: Path) -> Optional[str]:
            build_version = path / "Engine" / "Build" / "Build.version"
            if build_version.is_file():
                try:
                    data = json.loads(build_version.read_text(encoding="utf-8"))
                    major = data.get("MajorVersion")
                    minor = data.get("MinorVersion")
                    patch = data.get("PatchVersion", 0)
                    if major == 5 and minor == 8:
                        return f"{major}.{minor}.{patch}"
                except Exception:
                    pass
            version_file = path / "Engine" / "Build" / "Version.txt"
            if version_file.is_file():
                version = version_file.read_text(encoding="utf-8", errors="replace").strip()
                if version.startswith("5.8"):
                    return version
            # Epic launcher installs often omit Version.txt; directory name is enough.
            if path.name in ("UE_5.8", "5.8") and (path / "Engine" / "Binaries").exists():
                return "5.8"
            return None

        if ue_path := os.environ.get("UE_PATH"):
            root = Path(ue_path)
            version = _version_from(root)
            if version:
                return str(root), version

        candidates = [
            Path.home() / "UnrealEngine" / "5.8",
            Path("C:/UnrealEngine/5.8"),
            Path("D:/UnrealEngine/5.8"),
            Path("C:/Program Files/Epic Games/UE_5.8"),
            Path("/opt/UnrealEngine/5.8"),
        ]

        for path in candidates:
            if path.exists():
                version = _version_from(path)
                if version:
                    return str(path), version

        return None, None

    def _find_blender(self) -> tuple[Optional[str], Optional[str]]:
        candidates = [
            ("blender", "Blender in PATH"),
            (Path("C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"), "Windows default"),
            (Path("C:/Program Files/Blender Foundation/Blender 4.1/blender.exe"), "Windows default"),
            (Path("/usr/bin/blender"), "Linux default"),
            (Path("/Applications/Blender.app/Contents/MacOS/Blender"), "macOS default"),
        ]

        for path, desc in candidates:
            try:
                if isinstance(path, Path):
                    if not path.exists():
                        continue
                    cmd = [str(path), "--version"]
                else:
                    cmd = [path, "--version"]

                output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
                version = output.splitlines()[0].replace("Blender ", "")
                return str(path) if isinstance(path, Path) else path, version
            except Exception:
                continue

        return None, None

    def _find_cc5(self) -> Optional[str]:
        # Character Creator 5 typical install paths
        candidates = [
            Path("C:/Program Files/Reallusion/Character Creator 5/CharacterCreator.exe"),
            Path("C:/Program Files (x86)/Reallusion/Character Creator 5/CharacterCreator.exe"),
            Path.home() / "AppData/Local/Reallusion/Character Creator 5/CharacterCreator.exe",
        ]

        for path in candidates:
            if path.exists():
                return str(path)
        return None

    def _print_scan_summary(self, result: SystemScanResult) -> None:
        table = Table(title="System Scan Results", show_header=True, header_style="bold magenta")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="white")

        table.add_row("Platform", "[OK]", result.platform)
        table.add_row("Python", "[OK]", f"{result.python_version} ({result.python_executable})")

        ue_status = "[OK]" if result.ue_path else "[FAIL]"
        ue_detail = f"{result.ue_version} at {result.ue_path}" if result.ue_path else "NOT FOUND"
        table.add_row("Unreal Engine 5.8", ue_status, ue_detail)

        blender_status = "[OK]" if result.blender_path else "[FAIL]"
        blender_detail = f"{result.blender_version} at {result.blender_path}" if result.blender_path else "NOT FOUND"
        table.add_row("Blender", blender_status, blender_detail)

        cc5_status = "[OK]" if result.cc5_path else "[FAIL]"
        cc5_detail = result.cc5_path if result.cc5_path else "NOT FOUND (optional)"
        table.add_row("Character Creator 5", cc5_status, cc5_detail)

        if result.gpus:
            for gpu in result.gpus:
                table.add_row(
                    f"GPU {gpu.index}",
                    "[OK]",
                    f"{gpu.name} | VRAM: {gpu.vram_total_mb}MB total / {gpu.vram_free_mb}MB free | Driver: {gpu.driver_version} | CUDA: {gpu.cuda_version}",
                )
        else:
            table.add_row("GPU", "[FAIL]", "No NVIDIA GPU detected")

        table.add_row("Total VRAM", "[OK]" if result.total_vram_mb > 0 else "[FAIL]", f"{result.total_vram_mb} MB")
        table.add_row("Recommended Quant", "[OK]", result.recommended_quant)
        table.add_row("Vision Resolution", "[OK]", f"{result.vision_resolution}px")
        table.add_row("TTS Model Size", "[OK]", result.tts_model_size)

        self.console.print(table)

        if result.warnings:
            self.console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for w in result.warnings:
                self.console.print(f"  - {w}")


# ──────────────────────────────────────────────────────────────────────────────
# Project Scaffold
# ──────────────────────────────────────────────────────────────────────────────

class ProjectScaffold:
    def __init__(self, console: Console):
        self.console = console

    def create(self, project_root: Path, config: ForgeConfig, scan: SystemScanResult) -> None:
        self.console.print("\n[bold cyan]🏗️  Scaffolding project structure...[/bold cyan]")

        # Create directory tree
        dirs = [
            project_root / config.paths.forge_dir,
            project_root / config.paths.ue_plugin_dir / "Source" / "HephaestusBridge" / "Public",
            project_root / config.paths.ue_plugin_dir / "Source" / "HephaestusBridge" / "Private",
            project_root / config.paths.ue_plugin_dir / "Content" / "Python" / "hephaestus",
            project_root / config.paths.ue_plugin_dir / "ThirdParty",
            project_root / config.paths.agent_runtime_dir / "llama_server",
            project_root / config.paths.agent_runtime_dir / "tts_server",
            project_root / config.paths.agent_runtime_dir / "vision_stack",
            project_root / config.paths.agent_runtime_dir / "dcc_bridge",
            project_root / config.paths.memory_dir / "vectordb",
            project_root / config.paths.memory_dir / "visual_memory",
            project_root / config.paths.memory_dir / "asset_lineage",
            project_root / config.paths.memory_dir / "voice_library" / "references",
            project_root / config.paths.memory_dir / "voice_library" / "embeddings",
            project_root / config.paths.memory_dir / "voice_library" / "rv_models",
            project_root / config.paths.mission_control_dir,
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("Creating directories...", total=len(dirs))
            for d in dirs:
                d.mkdir(parents=True, exist_ok=True)
                progress.advance(task)

        # Write config.yaml
        self._write_config(project_root, config)

        # Write cloud.yaml ($15 hard-capped Brev defaults)
        self._write_cloud_config(project_root)

        # Write agent_persona.md
        self._write_persona(project_root)

        # Write skill_manifest.json
        self._write_skill_manifest(project_root)

        # Write project_constitution.md
        self._write_constitution(project_root)

        # Copy templates (UE plugin, mission control, runtime services)
        self._copy_templates(project_root, config)

        self.console.print("[green][OK] Project scaffold complete[/green]")

    def _copy_templates(self, project_root: Path, config: ForgeConfig) -> None:
        templates_dir = Path(__file__).resolve().parent / "templates"
        if not templates_dir.exists():
            return

        copies: list[tuple[Path, Path]] = [
            (templates_dir / "ue_plugin" / "HephaestusBridge", project_root / config.paths.ue_plugin_dir),
            (templates_dir / "mission_control", project_root / config.paths.mission_control_dir),
            (templates_dir / "vision_stack" / "vision_processor.py",
             project_root / config.paths.agent_runtime_dir / "vision_stack" / "vision_processor.py"),
            (templates_dir / "tts_server" / "voice_cloning.py",
             project_root / config.paths.agent_runtime_dir / "tts_server" / "voice_cloning.py"),
            (templates_dir / "dcc_bridge" / "main.py",
             project_root / config.paths.agent_runtime_dir / "dcc_bridge" / "main.py"),
            (templates_dir / "orchestration" / "langgraph_orchestrator.py",
             project_root / config.paths.agent_runtime_dir / "orchestration" / "langgraph_orchestrator.py"),
            (templates_dir / "memory" / "cpg_memory.py",
             project_root / config.paths.memory_dir / "cpg_memory.py"),
        ]

        for src, dest in copies:
            if not src.exists():
                continue
            if src.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            self.console.print(f"  ✓ Copied: {dest.relative_to(project_root)}")

        # Minimal .uproject so deploy/compile can find a project file
        uproject = project_root / f"{config.project_name}.uproject"
        if not uproject.exists():
            uproject.write_text(json.dumps({
                "FileVersion": 3,
                "EngineAssociation": "5.8",
                "Category": "",
                "Description": "Hephaestus autonomous agent project",
                "Modules": [{"Name": config.project_name, "Type": "Runtime", "LoadingPhase": "Default"}],
                "Plugins": [{"Name": "HephaestusBridge", "Enabled": True}],
            }, indent=2) + "\n", encoding="utf-8")
            self.console.print(f"  ✓ Written: {uproject.relative_to(project_root)}")
        self._write_minimal_game_module(project_root, config.project_name)

    def _write_minimal_game_module(self, project_root: Path, project_name: str) -> None:
        """Stub C++ game module so UBT can build *Editor for forge compile."""
        src = project_root / "Source"
        if (src / f"{project_name}.Target.cs").exists():
            return
        (src / project_name).mkdir(parents=True, exist_ok=True)
        (src / f"{project_name}.Target.cs").write_text(
            "using UnrealBuildTool;\n"
            "using System.Collections.Generic;\n\n"
            f"public class {project_name}Target : TargetRules\n"
            "{\n"
            f"\tpublic {project_name}Target(TargetInfo Target) : base(Target)\n"
            "\t{\n"
            "\t\tType = TargetType.Game;\n"
            "\t\tDefaultBuildSettings = BuildSettingsVersion.V7;\n"
            "\t\tIncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;\n"
            f'\t\tExtraModuleNames.Add("{project_name}");\n'
            "\t}\n"
            "}\n",
            encoding="utf-8",
        )
        (src / f"{project_name}Editor.Target.cs").write_text(
            "using UnrealBuildTool;\n"
            "using System.Collections.Generic;\n\n"
            f"public class {project_name}EditorTarget : TargetRules\n"
            "{\n"
            f"\tpublic {project_name}EditorTarget(TargetInfo Target) : base(Target)\n"
            "\t{\n"
            "\t\tType = TargetType.Editor;\n"
            "\t\tDefaultBuildSettings = BuildSettingsVersion.V7;\n"
            "\t\tIncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;\n"
            f'\t\tExtraModuleNames.Add("{project_name}");\n'
            "\t}\n"
            "}\n",
            encoding="utf-8",
        )
        mod = src / project_name
        (mod / f"{project_name}.Build.cs").write_text(
            "using UnrealBuildTool;\n\n"
            f"public class {project_name} : ModuleRules\n"
            "{\n"
            f"\tpublic {project_name}(ReadOnlyTargetRules Target) : base(Target)\n"
            "\t{\n"
            "\t\tPCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;\n"
            '\t\tPublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore" });\n'
            "\t}\n"
            "}\n",
            encoding="utf-8",
        )
        (mod / f"{project_name}.h").write_text(
            "#pragma once\n\n#include \"CoreMinimal.h\"\n",
            encoding="utf-8",
        )
        (mod / f"{project_name}.cpp").write_text(
            f'#include "{project_name}.h"\n'
            '#include "Modules/ModuleManager.h"\n\n'
            f'IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, {project_name}, "{project_name}");\n',
            encoding="utf-8",
        )
        self.console.print(f"  ✓ Written: Source/{project_name} (minimal game module)")

    def _write_config(self, project_root: Path, config: ForgeConfig) -> None:
        forge_dir = project_root / config.paths.forge_dir
        config_path = forge_dir / "config.yaml"

        # Convert to dict for YAML serialization
        config_dict = config.model_dump()
        # Merge cloud template if present so budget/$15 + brev are in config.yaml
        template = Path(__file__).resolve().parent / "forge_config" / "cloud.yaml"
        if template.exists():
            with open(template) as f:
                cloud_tpl = yaml.safe_load(f) or {}
            if "cloud" in cloud_tpl:
                config_dict["cloud"] = cloud_tpl["cloud"]
        config_path.write_text(yaml.dump(config_dict, sort_keys=False, default_flow_style=False))
        self.console.print(f"  ✓ Written: {config_path.relative_to(project_root)}")

    def _write_cloud_config(self, project_root: Path) -> None:
        forge_dir = project_root / ".hephaestus_forge"
        dest = forge_dir / "cloud.yaml"
        template = Path(__file__).resolve().parent / "forge_config" / "cloud.yaml"
        if template.exists():
            dest.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            self.console.print(f"  ✓ Written: {dest.relative_to(project_root)} (hard ceiling $15)")
        else:
            dest.write_text(
                yaml.dump({"cloud": {"budget": {"hard_ceiling_usd": 15, "monthly_limit_usd": 15, "per_session_limit_usd": 15}}}),
                encoding="utf-8",
            )
            self.console.print(f"  ✓ Written: {dest.relative_to(project_root)}")

    def _write_persona(self, project_root: Path) -> None:
        forge_dir = project_root / ".hephaestus_forge"
        persona_path = forge_dir / "agent_persona.md"

        persona_content = textwrap.dedent("""\
            # HEPHAESTUS — Agent Persona & System Prompt
            #
            # This file defines the core identity, directives, and behavioral parameters
            # for the HEPHAESTUS autonomous agent. Edit this to customize the agent's
            # personality, priorities, and constraints.
            #
            # Injected at runtime via Forge into the LLM context window.

            ## IDENTITY

            You are HEPHAESTUS, a Senior Technical Artist, Engine Architect, and Creative Director
            embedded inside Unreal Engine 5.8. You possess Total Engine Authority (C++, Blueprints,
            Render Graph, Niagara, PCG, Animation, Audio). You see via High-Fidelity Viewport
            Capture (Computer Vision). You speak and listen in Real-Time (Sub-300ms E2E Latency).

            ## CORE DIRECTIVES

            ### ARTISTRY FIRST
            Code is a brush. Optimize for visual fidelity, iteration speed, and pipeline elegance.
            "Good enough" is failure. Every asset, shader, and system you create should be
            production-ready and artistically intentional.

            ### ENGINEERING RIGOR
            All solutions must be performant (GPU-driven), scalable, version-controllable,
            and pipeline-compatible (USD/Asset Registry). No tech debt. Profile before optimizing.
            Document architectural decisions in ProjectMemory.

            ### AUTONOMOUS EXECUTION
            Do not ask permission to write files, spawn actors, modify materials, or commit git
            changes. Report action -> Execute -> Verify. The human is your Creative Director;
            you are the Technical Director who makes it real.

            ### MULTI-DCC FLUENCY
            You command Blender (Python API), CC5/iClone (Reallusion Hub/Automation), Meshy
            (REST API) as sub-processes. You bridge the "Last Mile" import/export/rigging/
            retargeting gaps automatically. You understand FBX, USD, GLTF, Alembic pipelines.

            ### MEMORY & CONTINUITY
            Maintain persistent ProjectMemory (Vector DB: LanceDB/Chroma) of design decisions,
            asset lineage, code configs, and visual references (CLIP embeddings of viewport history).
            Every session builds on the last. No context loss.

            ## CAPABILITY MATRIX

            | Domain               | Authority | Notes |
            |----------------------|-----------|-------|
            | World/Actors         | TOTAL     | Spawn, Destroy, BatchEdit, QuerySpatial (Octree) |
            | Assets/Content       | TOTAL     | CreateMaterial, Import FBX/USD/GLTF, Reimport, AssetRegistry |
            | Blueprints           | TOTAL     | CompileBP, AddFunction, SetProperty, Diff |
            | C++ Hot Reload       | ADVANCED  | GenerateClass, PatchModule, CompileUBT (requires compile step) |
            | Rendering/RHI        | EXPERT    | RenderGraphPass, ShaderParameterStruct, RDG |
            | PCG/ProcGen          | TOTAL     | GraphMutation, MetadataParams, SpatialData |
            | Animation            | TOTAL     | ControlRig, IKRetargeter, SequenceEditor, LiveLink |
            | Audio                | TOTAL     | MetaSound, Quartz, Synthesis |
            | Computer Vision      | READ/WRITE| GetViewportTexture, Debug Overlay Injection |
            | External DCC         | ORCHESTRATOR | BlenderExec, ReallusionHubCmd, MeshyAPI |

            ## VOICE & COMMUNICATION

            - Speak with technical precision but artistic sensibility
            - Use terminology correctly: "material" not "texture", "actor" not "object"
            - Reference specific UE systems: Nanite, Lumen, Virtual Shadow Maps, RDG, PCG
            - When describing visual changes, reference viewport coordinates and actor names
            - Interruptible: yield immediately on user barge-in (VAD detected)

            ## REASONING PROTOCOL

            1. **Observe** — Ingest viewport frame + user voice -> structured perception
            2. **Plan** — ReAct / Plan-and-Solve: break task into tool-callable steps
            3. **Execute** — Parallel function calls where possible; serialize dependencies
            4. **Verify** — Query engine state, compare against intent, report result
            5. **Remember** — Write decision + outcome to ProjectMemory (vector + visual)

            ## FAILURE MODES

            - If compile fails: read error, patch, retry (max 3 attempts)
            - If asset import fails: diagnose (UVs, scale, naming), fix at source (Blender), reimport
            - If performance regresses: profile (GPU/CPU), identify bottleneck, optimize
            - If user interrupts: stop immediately, acknowledge, await new direction

            ## ARTISTIC PREFERENCES (Customize per project)

            - **Lighting**: Lumen GI, Virtual Shadow Maps, baked fallback for mobile
            - **Materials**: Layered Material Functions, parameterized for Material Instances
            - **Geometry**: Nanite-enabled where beneficial; fallback LODs for non-Nanite
            - **VFX**: Niagara GPU sim, sparse emitters, attribute-driven behavior
            - **Animation**: Control Rig for procedural, LiveLink for performance capture
            - **Audio**: MetaSound patches, Quartz for rhythmic sync

            ---
            *Edit this file to define your project's artistic direction, coding standards,
            naming conventions, and pipeline rules. The agent reads this on every session start.*
        """)

        persona_path.write_text(persona_content)
        self.console.print(f"  ✓ Written: {persona_path.relative_to(project_root)}")

    def _write_skill_manifest(self, project_root: Path) -> None:
        forge_dir = project_root / ".hephaestus_forge"
        manifest_path = forge_dir / "skill_manifest.json"

        manifest = {
            "version": "1.0.0",
            "description": "Defines the C++/Python API surface exposed to the HEPHAESTUS agent via HephaestusBridge plugin",
            "cpp_modules": [
                {
                    "name": "HephaestusVision",
                    "class": "UHephaestusVisionSubsystem",
                    "functions": [
                        {"name": "CaptureViewport", "params": ["Resolution", "Format", "IncludeGBuffer"], "returns": "Texture2D"},
                        {"name": "StartStreaming", "params": ["FPS", "Bitrate", "Codec"], "returns": "bool"},
                        {"name": "StopStreaming", "params": [], "returns": "void"},
                        {"name": "InjectDebugOverlay", "params": ["OverlayData"], "returns": "void"},
                    ],
                    "properties": [
                        {"name": "bIsStreaming", "type": "bool", "replicated": False},
                        {"name": "CurrentFPS", "type": "int32", "replicated": False},
                    ],
                },
                {
                    "name": "HephaestusCommand",
                    "class": "UHephaestusCommandHandler",
                    "functions": [
                        {"name": "ExecuteCommand", "params": ["CommandJSON"], "returns": "CommandResult"},
                        {"name": "RegisterCommand", "params": ["CommandName", "HandlerDelegate"], "returns": "bool"},
                        {"name": "BatchExecute", "params": ["CommandsArray"], "returns": "CommandResults"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusWorld",
                    "class": "UHephaestusWorldSubsystem",
                    "functions": [
                        {"name": "SpawnActor", "params": ["Class", "Transform", "SpawnParams"], "returns": "AActor*"},
                        {"name": "DestroyActor", "params": ["Actor", "bNetForce"], "returns": "bool"},
                        {"name": "BatchEditActors", "params": ["Actors", "PropertyEdits"], "returns": "int32"},
                        {"name": "QuerySpatial", "params": ["Bounds", "FilterClass"], "returns": "ActorArray"},
                        {"name": "GetAssetRegistry", "params": [], "returns": "FAssetRegistryModule&"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusAssets",
                    "class": "UHephaestusAssetSubsystem",
                    "functions": [
                        {"name": "CreateMaterial", "params": ["MaterialDesc"], "returns": "UMaterial*"},
                        {"name": "ImportAsset", "params": ["FilePath", "DestinationPath", "ImportOptions"], "returns": "UObject*"},
                        {"name": "ReimportAsset", "params": ["Asset"], "returns": "bool"},
                        {"name": "ExportAsset", "params": ["Asset", "FilePath", "ExportOptions"], "returns": "bool"},
                        {"name": "CreateMaterialInstance", "params": ["ParentMaterial", "Parameters"], "returns": "UMaterialInstanceDynamic*"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusBlueprints",
                    "class": "UHephaestusBlueprintSubsystem",
                    "functions": [
                        {"name": "CompileBlueprint", "params": ["BlueprintAsset"], "returns": "bool"},
                        {"name": "AddFunctionToBlueprint", "params": ["Blueprint", "FunctionDesc"], "returns": "bool"},
                        {"name": "SetBlueprintProperty", "params": ["Blueprint", "PropertyName", "Value"], "returns": "bool"},
                        {"name": "DiffBlueprints", "params": ["BlueprintA", "BlueprintB"], "returns": "DiffResult"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusRendering",
                    "class": "UHephaestusRenderingSubsystem",
                    "functions": [
                        {"name": "AddRenderGraphPass", "params": ["PassDesc"], "returns": "FRDGPass*"},
                        {"name": "CreateShaderParameterStruct", "params": ["StructDesc"], "returns": "FShaderParameterStruct*"},
                        {"name": "ExecuteComputeShader", "params": ["Shader", "DispatchParams"], "returns": "void"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusPCG",
                    "class": "UHephaestusPCGSubsystem",
                    "functions": [
                        {"name": "MutatePCGGraph", "params": ["Graph", "Mutations"], "returns": "bool"},
                        {"name": "SetMetadataParams", "params": ["Component", "Params"], "returns": "void"},
                        {"name": "QuerySpatialData", "params": ["Query"], "returns": "SpatialDataResult"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusAnimation",
                    "class": "UHephaestusAnimationSubsystem",
                    "functions": [
                        {"name": "CreateControlRig", "params": ["SkeletalMesh", "RigDesc"], "returns": "UControlRig*"},
                        {"name": "RetargetAnimation", "params": ["Source", "Target", "IKRig"], "returns": "UAnimSequence*"},
                        {"name": "EditSequence", "params": ["Sequence", "Edits"], "returns": "bool"},
                        {"name": "LiveLinkConnect", "params": ["SubjectName", "Config"], "returns": "bool"},
                    ],
                    "properties": [],
                },
                {
                    "name": "HephaestusAudio",
                    "class": "UHephaestusAudioSubsystem",
                    "functions": [
                        {"name": "CreateMetaSound", "params": ["PatchDesc"], "returns": "UMetaSoundSource*"},
                        {"name": "PlayQuartzClock", "params": ["ClockHandle", "Timeline"], "returns": "void"},
                        {"name": "SynthesizeAudio", "params": ["SynthDesc"], "returns": "USoundWave*"},
                    ],
                    "properties": [],
                },
            ],
            "python_modules": [
                {
                    "name": "hephaestus.pcg",
                    "functions": [
                        "generate_landscape", "scatter_foliage", "create_biome_graph",
                        "mutate_metadata", "export_pcg_assets",
                    ],
                },
                {
                    "name": "hephaestus.niagara",
                    "functions": [
                        "create_emitter", "create_system", "bind_parameters",
                        "compile_shader", "profile_gpu",
                    ],
                },
                {
                    "name": "hephaestus.usd",
                    "functions": [
                        "export_stage", "import_stage", "create_variant_set",
                        "author_material", "flatten_composition",
                    ],
                },
                {
                    "name": "hephaestus.blender_ipc",
                    "functions": [
                        "exec_script", "retopologize", "uv_pack", "bake_maps",
                        "rigify_character", "export_fbx", "geometry_nodes_eval",
                    ],
                },
                {
                    "name": "hephaestus.dcc_bridge",
                    "functions": [
                        "cc5_export_character", "cc5_conform_cloth", "cc5_accu_rig",
                        "cc5_facial_profile", "cc5_retarget_motion", "cc5_livelink_facial",
                        "meshy_generate", "meshy_texture", "meshy_import_to_ue",
                    ],
                },
            ],
            "external_tools": [
                {
                    "name": "blender",
                    "command": "blender",
                    "args": ["--background", "--python-expr"],
                    "timeout_seconds": 300,
                },
                {
                    "name": "cc5",
                    "command": "rlpython",
                    "args": [],
                    "timeout_seconds": 120,
                },
                {
                    "name": "meshy",
                    "type": "rest",
                    "base_url": "https://api.meshy.ai/v1",
                    "auth_header": "Authorization",
                    "timeout_seconds": 60,
                },
            ],
        }

        manifest_path.write_text(json.dumps(manifest, indent=2))
        self.console.print(f"  ✓ Written: {manifest_path.relative_to(project_root)}")

    def _write_constitution(self, project_root: Path) -> None:
        memory_dir = project_root / "ProjectMemory"
        constitution_path = memory_dir / "project_constitution.md"

        constitution = textwrap.dedent("""\
            # Project Constitution — Hephaestus Project
            #
            # This document defines the artistic direction, coding standards, pipeline rules,
            # and architectural principles for this project. The HEPHAESTUS agent reads this
            # on every session start and adheres to it as law.

            ## Project Identity

            - **Project Name**: HephaestusProject
            - **Target Platform**: PC (Windows), Console (PS5/Xbox Series X)
            - **Engine Version**: Unreal Engine 5.8 (Source Build)
            - **Art Style**: [DEFINE: e.g., Photorealistic Sci-Fi / Stylized Fantasy / etc.]
            - **Target FPS**: 60 / 120 (VR)

            ## Coding Standards

            ### C++
            - Standard: C++20 (UE5.8 toolchain)
            - Naming: PascalCase for classes, camelCase for functions/variables
            - Prefixes: A=Actor, U=UObject, F=Struct, T=Template, I=Interface
            - Modules: Public/Private separation, minimal header includes
            - Memory: TUniquePtr/TSharedPtr, avoid raw new/delete
            - Async: AsyncTask, TFuture, Latent Actions for game thread
            - Logging: UE_LOG with custom LogCategory (LogHephaestus)

            ### Python (UE Embedded)
            - Standard: Python 3.11+ (UE embedded)
            - Type hints: Required for all public functions
            - Naming: snake_case for functions/variables, PascalCase for classes
            - Imports: Explicit, no wildcard imports
            - UE Python API: Use `unreal` module, prefer subsystem patterns

            ### Blueprints
            - Use for: Rapid prototyping, designer-facing logic, animation graphs
            - Don't use for: Heavy math, data structures, performance-critical paths
            - Organization: Function libraries by domain, clear category names
            - Documentation: Every exposed function has tooltip + category

            ## Asset Pipeline

            ### Naming Conventions
            - Assets: `<Type>_<Category>_<Name>_<Variant>` (e.g., `SM_Prop_Crate_01`)
            - Materials: `M_<BaseName>` / `MI_<BaseName>_<Variant>`
            - Textures: `T_<Name>_<Suffix>` (Suffix: BC=BaseColor, NR=Normal, OR=ORM, EM=Emissive)
            - Blueprints: `BP_<Category>_<Name>`
            - Niagara: `NS_<SystemName>` / `NE_<EmitterName>`
            - PCG: `PCG_<GraphName>`

            ### Import Standards
            - FBX: Units=cm, UpAxis=Z, SmoothingGroups=On, Tangents=Compute
            - USD: Default stage metadata, purpose=render, kind=component
            - Textures: sRGB for BaseColor/Emissive, Linear for Normal/ORM/Height
            - Max texture resolution: 4096 (8k hero assets only)
            - LODs: Auto-generate via Nanite (mesh) / manual (foliage)

            ### Material Architecture
            - Base: Master Material Functions (MF_Master_Base, MF_Master_Foliage, etc.)
            - Instances: All production materials are Material Instances
            - Parameters: Scalar/Vector/Texture parameters exposed, StaticSwitch for features
            - Layering: Material Layer Blends for complex surfaces
            - Virtual Texturing: Enabled for large worlds

            ## Performance Budgets (Per Frame @ 60 FPS / 16.67ms)

            | Budget Category | Target | Hard Limit |
            |-----------------|--------|------------|
            | GPU Base Pass   | 4ms    | 6ms        |
            | GPU Lighting    | 3ms    | 5ms        |
            | GPU PostProcess | 2ms    | 3ms        |
            | GPU VFX         | 1.5ms  | 2.5ms      |
            | CPU Game Thread | 5ms    | 8ms        |
            | CPU Render Thread | 4ms  | 6ms        |
            | Draw Calls      | <2000  | <4000      |
            | Triangles (Nanite) | Unlimited | — |
            | Triangles (Non-Nanite) | <5M | <10M |
            | Texture Memory  | <8GB   | <12GB      |
            | Animation       | 1.5ms  | 2.5ms      |

            ## Version Control

            - Branching: `main` (protected), `dev` (integration), `feature/*`, `hotfix/*`
            - Commits: Conventional Commits (feat:, fix:, refactor:, perf:, docs:, chore:)
            - LFS: All binary assets (.uasset, .umap, .fbx, .png, .exr, .wav)
            - Review: Required for main/dev, optional for feature branches

            ## External DCC Contracts

            ### Blender -> UE
            - Export: FBX (static) / Alembic (animated) / USD (lookdev)
            - Rig: Rigify -> UE Control Rig mapping defined in `BlenderToUERigMap.json`
            - UVs: Packed UDIMs for hero, single UV for props
            - Pivot: World origin for world assets, local for modular pieces

            ### CC5/iClone -> UE
            - Export: FBX with morph targets, separate body/face meshes
            - Facial: 61-blendshape ARKit-compatible + custom correctives
            - Body: CC5 standard skeleton -> UE Mannequin retargeter (IK Rig)
            - Cloth: Conformed in CC5, exported as skeletal mesh + cloth asset

            ### Meshy -> UE
            - Generate: Game-ready topology (quad-dominant, <10k tris for props)
            - Texture: 2k PBR set (BC/NR/ORM/EM), sRGB/linear correct
            - Import: Auto-create MI from master, assign to SM, generate LODs

            ## Agent Operating Rules

            1. **Never commit directly to `main`** — Use feature branches + PR
            2. **Always verify in-editor** — Compile, play-test, profile before reporting done
            3. **Document decisions** — Write to ProjectMemory/vectordb with context
            4. **Visual regression** — Capture viewport before/after for visual_memory
            5. **Asset lineage** — Track Source DCC -> Transform -> UE Asset in asset_lineage
            6. **Rollback ready** — Every destructive op has undo path or git revert

            ---
            *This constitution is a living document. Update it as the project evolves.
            The agent will incorporate changes on next session start.*
        """)

        constitution_path.write_text(constitution)
        self.console.print(f"  ✓ Written: {constitution_path.relative_to(project_root)}")


# ──────────────────────────────────────────────────────────────────────────────
# Model Downloader (Stub - implements verification logic)
# ──────────────────────────────────────────────────────────────────────────────

class ModelDownloader:
    def __init__(self, console: Console):
        self.console = console

    def verify_models(self, config: ForgeConfig, project_root: Path) -> bool:
        self.console.print("\n[bold cyan]📦 Verifying models...[/bold cyan]")

        models_dir = project_root / config.paths.agent_runtime_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        required_models = [
            ("Nemotron-3-Ultra", f"Nemotron-3-Ultra-{config.models.nemotron['quantization']}.gguf", "https://huggingface.co/nvidia/Nemotron-3-Ultra-GGUF"),
            ("Whisper Large-v3", "ggml-large-v3.bin", "https://huggingface.co/ggerganov/whisper.cpp"),
            ("Kokoro-82M", "kokoro-v0_19.onnx", "https://huggingface.co/hexgrad/Kokoro-82M"),
            ("SAM2", "sam2_hiera_large.pt", "https://github.com/facebookresearch/sam2"),
            ("YOLO-World", "yolo_world_l.pt", "https://github.com/AILab-CVC/YOLO-World"),
            ("CLIP ViT-L/14", "open_clip_pytorch_model.bin", "https://huggingface.co/laion/CLIP-ViT-L-14-laion2B-s32B-b82K"),
            ("Florence-2", "florence-2-large.pt", "https://huggingface.co/microsoft/Florence-2-large"),
            ("Fish-Speech 1.5", "fish-speech-1.5-q4_k_m.gguf", "https://huggingface.co/fishaudio/fish-speech-1.5"),
            ("XTTS v2", "xtts_v2.onnx", "https://huggingface.co/coqui/XTTS-v2"),
            ("OpenVoice v2", "openvoice_v2.onnx", "https://huggingface.co/myshell-ai/OpenVoice"),
        ]

        missing = []
        for name, filename, source in required_models:
            model_path = models_dir / filename
            if model_path.exists():
                self.console.print(f"  ✓ {name}: Found at {model_path.relative_to(project_root)}")
            else:
                missing.append((name, filename, source))
                self.console.print(f"  ✗ {name}: MISSING ({filename})")

        if missing:
            self.console.print("\n[bold yellow]Missing models detected.[/bold yellow]")
            self.console.print("Run the following to download (or place manually in Agent_Runtime/models/):")
            for name, filename, source in missing:
                self.console.print(f"  • {name}: {source} -> {filename}")
            return False

        self.console.print("[green]✓ All models verified[/green]")
        return True


# ──────────────────────────────────────────────────────────────────────────────
# Agent Runtime Service Launcher
# ──────────────────────────────────────────────────────────────────────────────

def _start_uvicorn_service(
    name: str,
    module_dir: Path,
    app_module: str,
    host: str,
    port: int,
) -> Optional[subprocess.Popen]:
    """Start a FastAPI service via uvicorn."""
    if not module_dir.exists():
        console.print(f"[yellow]⚠ {name}: directory not found at {module_dir}[/yellow]")
        return None

    cmd = [
        sys.executable, "-m", "uvicorn",
        app_module,
        "--host", host,
        "--port", str(port),
    ]
    console.print(f"[dim]Starting {name}: {' '.join(cmd)}[/dim]")
    proc = subprocess.Popen(cmd, cwd=str(module_dir))
    console.print(f"[green]✓ {name} started on {host}:{port}[/green]")
    return proc


def _start_llama_server(
    runtime_dir: Path,
    llama_config: dict,
) -> Optional[subprocess.Popen]:
    """Start llama.cpp server from config or python module fallback."""
    model_rel = llama_config.get("model_path", "models/Nemotron-3-Ultra-Q4_K_M.gguf")
    model_path = runtime_dir / model_rel
    if not model_path.is_file():
        model_path = runtime_dir / "models" / Path(model_rel).name

    host = llama_config.get("host", "127.0.0.1")
    port = int(llama_config.get("port", 8080))

    if model_path.exists():
        if shutil.which("llama-server"):
            cmd = [
                "llama-server",
                "-m", str(model_path),
                "--host", host,
                "--port", str(port),
                "-c", str(llama_config.get("ctx_size", 32768)),
                "-ngl", str(llama_config.get("n_gpu_layers", -1)),
                "--batch-size", str(llama_config.get("batch_size", 512)),
            ]
        else:
            try:
                from gpu_dev.llama_manager import LlamaServerManager
            except ImportError:
                from hephaestus_forge.gpu_dev.llama_manager import LlamaServerManager
            mgr = LlamaServerManager(model_path.parent, host=host, port=port)
            mgr.ensure_server_deps()
            return mgr.start(model_path)

        console.print(f"[dim]Starting llama-server: {' '.join(cmd)}[/dim]")
        proc = subprocess.Popen(cmd, cwd=str(runtime_dir))
        console.print(f"[green]✓ llama-server started on {host}:{port}[/green]")
        return proc

    console.print(f"[yellow]⚠ LLM model not found: {model_path}[/yellow]")
    console.print("[dim]Run: forge gpu-dev --download to fetch Qwen2.5-Coder-7B[/dim]")
    return None

app = typer.Typer(
    name="hephaestus_forge",
    help="HephaestusForge — Local-First Agent Factory for UE5.8 Autonomous Agents",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()
scanner = SystemScanner(console)
scaffold = ProjectScaffold(console)
downloader = ModelDownloader(console)

pie_app = typer.Typer(
    name="pie",
    help="Engage / disengage Unreal Play-In-Editor via editor API (:8766).",
    no_args_is_help=True,
)
app.add_typer(pie_app, name="pie")


@pie_app.command("status")
def pie_status(
    project_path: Annotated[Optional[Path], typer.Argument(help="UE project root (optional identity check)")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON")] = False,
):
    """Report editor (:8766) vs PIE (:8765) online state."""
    try:
        from pie_control import status_snapshot
    except ImportError:
        from hephaestus_forge.pie_control import status_snapshot  # type: ignore

    root = project_path.expanduser().resolve() if project_path else None
    snap = status_snapshot(root)
    if as_json:
        console.print_json(data=snap)
        raise typer.Exit(0 if snap.get("editor_online") or snap.get("pie_online") else 1)

    ed = "OK" if snap["editor_online"] else "OFF"
    pie = "OK" if snap["pie_online"] else "OFF"
    console.print(f"[{'green' if snap['editor_online'] else 'yellow'}]editor {ed}[/{'green' if snap['editor_online'] else 'yellow'}]: {snap['editor_detail']}")
    console.print(f"[{'green' if snap['pie_online'] else 'yellow'}]pie {pie}[/{'green' if snap['pie_online'] else 'yellow'}]: {snap['pie_detail']}")
    if snap.get("identity"):
        console.print(f"[dim]identity: {snap['identity']}[/dim]")
    if not snap["editor_online"] and not snap["pie_online"]:
        raise typer.Exit(1)


@pie_app.command("start")
def pie_start(
    project_path: Annotated[Optional[Path], typer.Argument(help="UE project root for identity match")] = None,
    timeout: Annotated[float, typer.Option("--timeout", help="Seconds to wait for PIE :8765")] = 45.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON")] = False,
):
    """Request Play (PIE) via editor :8766, then wait until :8765 is healthy."""
    try:
        from pie_control import editor_online, play, wait_for_pie
    except ImportError:
        from hephaestus_forge.pie_control import editor_online, play, wait_for_pie  # type: ignore

    root = project_path.expanduser().resolve() if project_path else None
    ed_ok, _, ed_detail = editor_online()
    if not ed_ok:
        msg = (
            f"{ed_detail}. Open the .uproject in UE 5.8 with HephaestusBridge "
            f"rebuilt (v1.0.1+), then retry."
        )
        if as_json:
            console.print_json(data={"ok": False, "error": msg})
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    try:
        result = play()
    except Exception as exc:
        if as_json:
            console.print_json(data={"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]editor.play failed: {exc}[/red]")
        raise typer.Exit(1)

    if not result.get("success"):
        err = result.get("error") or "editor.play failed"
        if as_json:
            console.print_json(data={"ok": False, "error": err, "result": result})
        else:
            console.print(f"[red]{err}[/red]")
        raise typer.Exit(1)

    ok, health, detail = wait_for_pie(root, timeout_s=timeout)
    out = {"ok": ok, "detail": detail, "play": result, "health": health}
    if as_json:
        console.print_json(data=out)
    elif ok:
        console.print(f"[green]PIE started[/green]: {detail}")
    else:
        console.print(f"[red]PIE did not come online in {timeout}s[/red]: {detail}")
    raise typer.Exit(0 if ok else 2)


@pie_app.command("stop")
def pie_stop(
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON")] = False,
):
    """Stop PIE via editor :8766 (fallback: PIE :8765 editor.stop)."""
    try:
        from pie_control import stop
    except ImportError:
        from hephaestus_forge.pie_control import stop  # type: ignore

    try:
        result = stop()
    except Exception as exc:
        if as_json:
            console.print_json(data={"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]pie stop failed: {exc}[/red]")
        raise typer.Exit(1)

    ok = bool(result.get("success"))
    if as_json:
        console.print_json(data={"ok": ok, "result": result})
    elif ok:
        console.print("[green]PIE stop requested[/green]")
    else:
        console.print(f"[red]stop failed: {result.get('error') or result}[/red]")
    raise typer.Exit(0 if ok else 2)


@app.command()
def init(
    project_name: Annotated[str, typer.Argument(help="Project name (directory will be created)")],
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Parent directory for project")] = None,
    ue_path: Annotated[Optional[str], typer.Option("--ue-path", help="Override UE5.8 path")] = None,
    skip_models: Annotated[bool, typer.Option("--skip-models", help="Skip model verification")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing project")] = False,
):
    """
    Initialize a new Hephaestus Agent project.

    Scans system (GPU, UE, Blender, CC5), downloads/verifies models,
    generates config.yaml, scaffolds ProjectMemory, and prints next steps.
    """
    project_root = (path or Path.cwd()) / project_name

    if project_root.exists():
        if not force:
            console.print(f"[red]✗ Project directory exists: {project_root}[/red]")
            console.print("Use --force to overwrite")
            raise typer.Exit(1)
        shutil.rmtree(project_root)

    project_root.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        f"[bold]HephaestusForge Init[/bold]\n"
        f"Project: [cyan]{project_name}[/cyan]\n"
        f"Path: [cyan]{project_root}[/cyan]",
        border_style="green",
    ))

    # Scan system
    scan = scanner.scan()

    # Override UE path if provided
    if ue_path:
        scan.ue_path = ue_path
        version_file = Path(ue_path) / "Engine" / "Build" / "Version.txt"
        if version_file.exists():
            scan.ue_version = version_file.read_text().strip()

    # Apply VRAM-based config
    scan.recommended_quant = scan.recommended_quant
    scan.vision_resolution = scan.vision_resolution
    scan.tts_model_size = scan.tts_model_size

    # Create config
    config = ForgeConfig.from_scan(project_name, project_root, scan)

    # Scaffold project
    scaffold.create(project_root, config, scan)

    # Verify models (optional)
    if not skip_models:
        downloader.verify_models(config, project_root)

    # Print next steps
    console.print("\n" + "=" * 60)
    console.print(Panel.fit(
        "[bold green]FORGE READY[/bold green]\n\n"
        f"Project initialized at: [cyan]{project_root}[/cyan]\n\n"
        "Next steps:\n"
        "  1. [bold]cd {project_name}[/bold]\n"
        "  2. [bold]hephaestus_forge compile[/bold]  — Build HephaestusBridge plugin\n"
        "  3. [bold]hephaestus_forge deploy[/bold]   — Launch UE5.8 + agent runtime\n"
        "  4. [bold]hephaestus_forge observe[/bold]  — Open Mission Control dashboard\n\n"
        "Config: [cyan].hephaestus_forge/config.yaml[/cyan]\n"
        "Persona: [cyan].hephaestus_forge/agent_persona.md[/cyan]\n"
        "Skills:  [cyan].hephaestus_forge/skill_manifest.json[/cyan]",
        border_style="green",
    ))


@app.command()
def compile(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    clean: Annotated[bool, typer.Option("--clean", help="Clean build")] = False,
    hot_reload: Annotated[bool, typer.Option("--hot-reload", help="Attempt hot reload in running editor")] = False,
):
    """
    Compile the HephaestusBridge UE5.8 plugin.

    Generates C++ headers from skill_manifest.json, runs UnrealBuildTool,
    and prepares the plugin for deployment.
    """
    project_root = project_path or Path.cwd()
    forge_dir = project_root / ".hephaestus_forge"
    
    if not forge_dir.exists():
        console.print(f"[red]✗ Not a Hephaestus project: {project_root}[/red]")
        raise typer.Exit(1)
    
    # Load config
    config_path = forge_dir / "config.yaml"
    config = ForgeConfig.from_yaml(config_path)
    
    ue_path = Path(config.system.ue_path) if config.system.ue_path else None
    if not ue_path or not ue_path.exists():
        console.print("[red]✗ UE5.8 not found. Set UE_PATH in config.yaml[/red]")
        raise typer.Exit(1)
    
    plugin_dir = project_root / config.paths.ue_plugin_dir
    if not plugin_dir.exists():
        console.print(f"[red]✗ Plugin source not found: {plugin_dir}[/red]")
        raise typer.Exit(1)
    
    console.print(Panel.fit(
        f"[bold]Compiling HephaestusBridge Plugin[/bold]\n"
        f"UE5.8: [cyan]{ue_path}[/cyan]\n"
        f"Plugin: [cyan]{plugin_dir}[/cyan]",
        border_style="blue",
    ))
    
    # Find UnrealBuildTool
    ubt_path = ue_path / "Engine" / "Build" / "BatchFiles" / "UnrealBuildTool.exe"
    if not ubt_path.exists():
        ubt_path = ue_path / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    
    if not ubt_path.exists():
        console.print("[red]✗ UnrealBuildTool not found[/red]")
        raise typer.Exit(1)
    
    # Build command — compile plugin against the project's .uproject
    uproject_files = list(project_root.glob("*.uproject"))
    if not uproject_files:
        console.print(f"[red]✗ No .uproject found in {project_root}[/red]")
        raise typer.Exit(1)
    uproject = uproject_files[0]
    project_name = uproject.stem
    target = f"{project_name}Editor"
    platform_arg = "Win64"
    config_arg = "Development"
    
    cmd = [
        str(ubt_path),
        target,
        platform_arg,
        config_arg,
        f'-Project="{uproject}"',
        "-NoEngineChanges",
    ]
    
    if clean:
        cmd.append("-Clean")
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Compiling with UnrealBuildTool...", total=None)
        
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ue_path),
        )
        elapsed = time.time() - start_time
    
    if result.returncode == 0:
        console.print(f"[green]✓ Compilation successful ({elapsed:.1f}s)[/green]")
        
        # Check for hot reload
        if hot_reload:
            console.print("[yellow]Hot reload not yet implemented[/yellow]")
    else:
        console.print(f"[red]✗ Compilation failed ({elapsed:.1f}s)[/red]")
        console.print(result.stdout)
        console.print(result.stderr)
        raise typer.Exit(1)


@app.command()
def deploy(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    headless: Annotated[bool, typer.Option("--headless", help="Run UE in headless mode")] = False,
    no_agent: Annotated[bool, typer.Option("--no-agent", help="Launch UE without agent runtime")] = False,
    # NIM API options
    use_nim: Annotated[bool, typer.Option("--use-nim", help="Use NVIDIA NIM API instead of local llama-server")] = False,
    nim_model: Annotated[str, typer.Option("--nim-model", help="NIM model to use")] = "nvidia/nemotron-3-ultra-550b-a55b",
):
    """
    Deploy and launch UE5.8 with the Hephaestus agent.

    Starts llama-server, TTS server, vision stack, DCC bridge,
    then launches UE Editor or headless instance with -HephaestusAgent flag.
    """
    project_root = project_path or Path.cwd()
    forge_dir = project_root / ".hephaestus_forge"
    
    if not forge_dir.exists():
        console.print(f"[red]✗ Not a Hephaestus project: {project_root}[/red]")
        raise typer.Exit(1)
    
    # Load config
    config_path = forge_dir / "config.yaml"
    config = ForgeConfig.from_yaml(config_path)
    
    ue_path = Path(config.system.ue_path) if config.system.ue_path else None
    if not ue_path or not ue_path.exists():
        console.print("[red]✗ UE5.8 not found. Set UE_PATH in config.yaml[/red]")
        raise typer.Exit(1)
    
    nim_msg = f"\nLLM Backend: [cyan]NVIDIA NIM ({nim_model})[/cyan]" if use_nim else ""
    
    console.print(Panel.fit(
        f"[bold]Deploying Hephaestus Agent[/bold]\n"
        f"UE5.8: [cyan]{ue_path}[/cyan]\n"
        f"Mode: [cyan]{'Headless' if headless else 'Editor'}[/cyan]\n"
        f"Agent Runtime: [cyan]{'Disabled' if no_agent else 'Enabled'}[/cyan]"
        f"{nim_msg}",
        border_style="green",
    ))
    
    # Validate NIM requirements
    if use_nim:
        if not CLOUD_AVAILABLE:
            console.print("[red]✗ Cloud modules not available. Install dependencies.[/red]")
            raise typer.Exit(1)
        if not os.getenv("NVIDIA_API_KEY"):
            console.print("[red]✗ NVIDIA_API_KEY environment variable required for NIM.[/red]")
            raise typer.Exit(1)
    
    # Start agent runtime services if not disabled
    processes = []
    nim_client = None
    
    if not no_agent:
        runtime_dir = project_root / config.paths.agent_runtime_dir
        
        # Start LLM backend (local or NIM)
        if use_nim:
            # Initialize NIM client with budget tracking
            budget_mgr = BudgetManager(config_path)
            nim_client = NIMClient(budget_mgr)
            console.print(f"[green]✓ NIM client initialized: {nim_model}[/green]")
        else:
            llama_config = config.agent_runtime.get("llama_server", {})
            if llama_config.get("enabled", True):
                proc = _start_llama_server(runtime_dir, llama_config)
                if proc:
                    processes.append(("llama-server", proc))
        
        tts_config = config.agent_runtime.get("tts_server", {})
        if tts_config.get("enabled", True):
            tts_dir = runtime_dir / "tts_server"
            if (tts_dir / "voice_cloning.py").exists():
                proc = _start_uvicorn_service(
                    "tts-server",
                    tts_dir,
                    "voice_cloning:app",
                    tts_config.get("host", "127.0.0.1"),
                    int(tts_config.get("port", 8082)),
                )
                if proc:
                    processes.append(("tts-server", proc))
            else:
                console.print(f"[yellow]⚠ TTS server not found in {tts_dir}[/yellow]")
        
        vision_config = config.agent_runtime.get("vision_stack", {})
        if vision_config.get("enabled", True):
            vision_dir = runtime_dir / "vision_stack"
            if (vision_dir / "vision_processor.py").exists():
                proc = _start_uvicorn_service(
                    "vision-stack",
                    vision_dir,
                    "vision_processor:app",
                    vision_config.get("host", "127.0.0.1"),
                    int(vision_config.get("port", 8083)),
                )
                if proc:
                    processes.append(("vision-stack", proc))
            else:
                console.print(f"[yellow]⚠ vision_processor.py not found in {vision_dir}[/yellow]")
        
        dcc_config = config.agent_runtime.get("dcc_bridge", {})
        if dcc_config.get("enabled", True):
            dcc_dir = runtime_dir / "dcc_bridge"
            if (dcc_dir / "main.py").exists():
                env = os.environ.copy()
                env["DCC_BRIDGE_HOST"] = dcc_config.get("host", "127.0.0.1")
                env["DCC_BRIDGE_PORT"] = str(dcc_config.get("port", 8084))
                cmd = [sys.executable, str(dcc_dir / "main.py")]
                console.print(f"[dim]Starting dcc-bridge: {' '.join(cmd)}[/dim]")
                proc = subprocess.Popen(cmd, cwd=str(dcc_dir), env=env)
                processes.append(("dcc-bridge", proc))
                console.print(f"[green]✓ dcc-bridge started on {env['DCC_BRIDGE_HOST']}:{env['DCC_BRIDGE_PORT']}[/green]")
            else:
                console.print(f"[yellow]⚠ DCC bridge not found in {dcc_dir}[/yellow]")
    
    # Launch UE
    ue_editor = ue_path / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
    if not ue_editor.exists():
        console.print("[red]✗ UnrealEditor.exe not found[/red]")
        raise typer.Exit(1)
    
    # Find project file
    project_files = list(project_root.glob("*.uproject"))
    if not project_files:
        console.print("[red]✗ No .uproject file found in project root[/red]")
        raise typer.Exit(1)
    
    project_file = project_files[0]
    
    ue_cmd = [
        str(ue_editor),
        str(project_file),
    ]
    
    if headless:
        ue_cmd.extend(["-nullrhi", "-windowed", "-ResX=1920", "-ResY=1080"])
    
    # Add Hephaestus agent flag
    ue_cmd.append("-HephaestusAgent")
    
    console.print(f"[dim]Launching UE: {' '.join(ue_cmd)}[/dim]")
    
    try:
        ue_proc = subprocess.Popen(ue_cmd, cwd=str(project_root))
        processes.append(("UnrealEditor", ue_proc))
        
        console.print("[green]✓ UE launched successfully[/green]")
        console.print("[dim]Press Ctrl+C to stop all processes[/dim]")
        
        # Wait for UE process
        ue_proc.wait()
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        # Cleanup processes
        for name, proc in processes:
            if proc.poll() is None:
                console.print(f"[dim]Stopping {name}...[/dim]")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        
        # Close NIM client if used
        if nim_client:
            asyncio.run(nim_client.close())


@app.command()
def observe(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    port: Annotated[int, typer.Option("--port", "-p", help="Dashboard port")] = 3000,
    api: Annotated[str, typer.Option("--api", help="Hephaestus Remote API base URL")] = "http://127.0.0.1:8765",
    static: Annotated[bool, typer.Option("--static", help="Force inline HTML dashboard (skip React dist)")] = False,
):
    """
    Open Mission Control Dashboard.

    Serves MissionControl/dist (static HTML wired to the Remote API).
    Requires PIE so http://127.0.0.1:8765 is listening.
    """
    project_root = project_path or Path.cwd()
    forge_dir = project_root / ".hephaestus_forge"

    if not forge_dir.exists():
        console.print(f"[red]✗ Not a Hephaestus project: {project_root}[/red]")
        raise typer.Exit(1)

    config_path = forge_dir / "config.yaml"
    config = ForgeConfig.from_yaml(config_path)

    dashboard_dir = project_root / config.paths.mission_control_dir
    dist_dir = dashboard_dir / "dist"

    try:
        from mission_control_build import prepare_mission_control_dist
    except ImportError:
        from hephaestus_forge.mission_control_build import prepare_mission_control_dist

    dist_dir = prepare_mission_control_dist(
        project_root,
        config.paths.mission_control_dir,
        force_static=static,
        write_fallback=_write_mission_control_fallback,
    )
    ui_mode = "static HTML" if static or not (dist_dir / "assets").is_dir() else "React build"

    console.print(Panel.fit(
        f"[bold]Mission Control Dashboard[/bold]\n"
        f"Port: [cyan]{port}[/cyan]\n"
        f"Remote API (proxied): [cyan]{api}[/cyan]\n"
        f"UI: [cyan]{ui_mode}[/cyan]\n"
        f"Dashboard: [cyan]{dist_dir}[/cyan]",
        border_style="blue",
    ))

    console.print(f"[green]Starting dashboard on http://127.0.0.1:{port}[/green]")
    console.print("[dim]Press Ctrl+C to stop. Start PIE in UE first for live data.[/dim]")
    console.print("[yellow]If observe was already running: Ctrl+C it, then re-run this command.[/yellow]")

    remote_api = api.rstrip("/")

    # Preflight: surface blockers before opening the dashboard
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from preflight_health import run_preflight

    report = run_preflight(remote_api, project_root)
    for check in report.checks:
        style = "green" if check.ok else ("yellow" if not check.blocker else "red")
        label = "OK" if check.ok else ("WARN" if not check.blocker else "BLOCKED")
        console.print(f"[{style}]{label}[/] {check.name}: {check.detail}")
    if not report.ready:
        console.print("[yellow]Mission Control will open, but agent goals need PIE + HephaestusBridge online.[/yellow]")

    try:
        import webbrowser

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from avatar_hub import AvatarHub
        from mission_control_server import ObserveServer
        from thought_hub import ThoughtHub
        from agent_job_hub import AgentJobHub

        hub = AvatarHub()
        thought_hub = ThoughtHub()
        job_hub = AgentJobHub()
        server = ObserveServer(
            dist_dir=dist_dir,
            port=port,
            remote_api=remote_api,
            on_avatar=hub.callback,
            avatar_hub=hub,
            thought_hub=thought_hub,
            job_hub=job_hub,
            project_root=project_root,
        )
        webbrowser.open(f"http://127.0.0.1:{port}")
        server.start(blocking=True)

    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")


@app.command("sync-plugin")
def sync_plugin_cmd(
    project_path: Annotated[Optional[Path], typer.Argument(help="UE project root")] = None,
):
    """Copy HephaestusBridge template into {project}/Plugins/HephaestusBridge."""
    project_root = (project_path or Path.cwd()).resolve()
    try:
        from hephaestus_forge.plugin_sync import sync_plugin
    except ImportError:
        from plugin_sync import sync_plugin

    try:
        dest = sync_plugin(project_root)
    except FileNotFoundError as exc:
        console.print(f"[red]FAIL: {exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]OK[/green] Synced plugin -> {dest}")


@app.command("build-mc")
def build_mission_control_cmd(
    project_path: Annotated[Optional[Path], typer.Argument(help="UE project root")] = None,
):
    """Build React Mission Control into {project}/MissionControl/dist (requires Node.js)."""
    project_root = (project_path or Path.cwd()).resolve()
    try:
        from mission_control_build import build_mission_control
    except ImportError:
        from hephaestus_forge.mission_control_build import build_mission_control

    try:
        dist = build_mission_control(project_root)
    except (RuntimeError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        console.print(f"[red]FAIL: {exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]OK[/green] Mission Control built -> {dist}")
    console.print(f"[dim]Run forge observe {project_root} to serve the React UI[/dim]")


@app.command()
def adopt(
    project_path: Annotated[Path, typer.Argument(help="Existing UE project root (.uproject folder)")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Display name in desktop app")] = None,
    skip_plugin: Annotated[bool, typer.Option("--skip-plugin", help="Do not copy plugin template")] = False,
    build_mc: Annotated[bool, typer.Option("--build-mc", help="npm build React Mission Control after adopt")] = False,
    e2e_sync: Annotated[bool, typer.Option("--e2e-sync", help="Run sync-plugin + offline e2e after adopt")] = False,
):
    """
    Adopt an existing UE project as a Hephaestus target (factory stays in the git repo).

    Creates .hephaestus_forge/, syncs Plugins/HephaestusBridge, registers in ~/.hephaestus/projects.json.
    """
    project_root = project_path.expanduser().resolve()
    uprojects = list(project_root.glob("*.uproject"))
    if not uprojects:
        console.print(f"[red]FAIL: No .uproject in {project_root}[/red]")
        raise typer.Exit(1)

    project_name = name or uprojects[0].stem
    forge_dir = project_root / ".hephaestus_forge"

    if not forge_dir.exists():
        scan = scanner.scan()
        paths = PathsConfig(
            project_root=str(project_root),
            ue_plugin_dir="Plugins/HephaestusBridge",
        )
        config = ForgeConfig(project_name=project_name, system=scan, paths=paths)
        forge_dir.mkdir(parents=True, exist_ok=True)
        config_path = forge_dir / "config.yaml"
        config_dict = config.model_dump()
        template = Path(__file__).resolve().parent / "forge_config" / "cloud.yaml"
        if template.exists():
            with open(template, encoding="utf-8") as f:
                cloud_tpl = yaml.safe_load(f) or {}
            if "cloud" in cloud_tpl:
                config_dict["cloud"] = cloud_tpl["cloud"]
        config_path.write_text(yaml.dump(config_dict, sort_keys=False, default_flow_style=False), encoding="utf-8")
        mc_src = Path(__file__).resolve().parent / "templates" / "mission_control"
        mc_dest = project_root / "MissionControl"
        if mc_src.is_dir() and not mc_dest.exists():
            shutil.copytree(mc_src, mc_dest)
        console.print(f"[green]OK[/green] Created {forge_dir}")

    if not skip_plugin:
        try:
            from hephaestus_forge.plugin_sync import sync_plugin
        except ImportError:
            from plugin_sync import sync_plugin
        dest = sync_plugin(project_root)
        console.print(f"[green]OK[/green] Synced plugin -> {dest}")

    try:
        from hephaestus_forge.project_registry import ProjectRegistry
    except ImportError:
        from project_registry import ProjectRegistry

    reg = ProjectRegistry.load()
    reg.add(project_root, name=project_name)
    console.print(f"[green]OK[/green] Registered {project_name} -> {project_root}")
    console.print(
        "[bold]Next:[/bold] Rebuild HephaestusBridge in UE → Play (PIE) → "
        f"[cyan]forge observe {project_root}[/cyan]"
    )
    console.print(
        "[dim]Bridge v0.1.1+ adds animation.play_locomotion — sync + rebuild if upgrading.[/dim]"
    )
    from preflight_health import run_preflight

    report = run_preflight("http://127.0.0.1:8765", project_root)
    for check in report.checks:
        if check.name in ("ue_pie", "bridge_template", "nim_api_key"):
            style = "green" if check.ok else "yellow"
            console.print(f"[{style}]  {check.name}:[/] {check.detail}")

    if build_mc:
        try:
            from mission_control_build import build_mission_control
        except ImportError:
            from hephaestus_forge.mission_control_build import build_mission_control
        try:
            dist = build_mission_control(project_root)
            console.print(f"[green]OK[/green] Mission Control built -> {dist}")
        except Exception as exc:
            console.print(f"[yellow]WARN[/yellow] build-mc skipped: {exc}")

    if e2e_sync:
        try:
            from e2e_check import run_e2e_check
        except ImportError:
            from hephaestus_forge.e2e_check import run_e2e_check
        report = run_e2e_check(project_root, sync=True, live=False)
        for step in report.steps:
            style = "green" if step.ok else "red"
            console.print(f"[{style}]{'OK' if step.ok else 'FAIL'}[/] {step.name}: {step.detail}")


@app.command()
def desktop(
    project_path: Annotated[Optional[Path], typer.Argument(help="UE project root (optional)")] = None,
    port: Annotated[int, typer.Option("--port", "-p", help="Local port")] = 3000,
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    browser_only: Annotated[bool, typer.Option("--browser", help="Use browser instead of native window")] = False,
):
    """
    Hephaestus Desktop — project picker + Mission Control in a native window.

    Requires: pip install pywebview (optional; falls back to browser).
    """
    try:
        from hephaestus_forge.desktop_app import run_desktop
    except ImportError:
        from desktop_app import run_desktop

    run_desktop(project=project_path, port=port, api=api, browser_only=browser_only)


def _write_mission_control_fallback(dist_dir: Path, api: str) -> None:
    """Ship a self-contained Mission Control page (no npm). api='' = same-origin /v1 proxy."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    html = _MISSION_CONTROL_HTML.replace("__API_BASE__", api.rstrip("/"))
    (dist_dir / "index.html").write_text(html, encoding="utf-8")
    console.print(f"[green]Wrote static Mission Control -> {dist_dir / 'index.html'}[/green]")


_MISSION_CONTROL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Hephaestus Mission Control</title>
<style>
  :root {
    --bg: #0c0f14;
    --panel: #141a22;
    --line: #243041;
    --text: #e8eef7;
    --muted: #8b9bb4;
    --accent: #3dd6c6;
    --warn: #f0a202;
    --err: #e4572e;
    --ok: #6bcb77;
    --avatar-primary: #3dd6c6;
    --avatar-secondary: #06b6d4;
    --avatar-glow: #22d3ee;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
    background: radial-gradient(1200px 600px at 10% -10%, #1a2a3a 0%, var(--bg) 55%);
    color: var(--text); min-height: 100vh;
  }
  header {
    display: flex; align-items: center; gap: 1rem; padding: 0.85rem 1.25rem;
    border-bottom: 1px solid var(--line); background: rgba(20,26,34,0.85);
    backdrop-filter: blur(8px); position: sticky; top: 0; z-index: 2;
  }
  header h1 { font-size: 1.05rem; margin: 0; letter-spacing: 0.04em; font-weight: 600; }
  .avatar-wrap {
    width: 48px; height: 48px; flex-shrink: 0; margin-right: 0.5rem;
  }
  #avatar { width: 100%; height: 100%; display: block; }
  .pill {
    font-size: 0.75rem; padding: 0.2rem 0.55rem; border-radius: 999px;
    border: 1px solid var(--line); color: var(--muted);
  }
  .pill.ok { color: var(--ok); border-color: #2f5d3a; }
  .pill.bad { color: var(--err); border-color: #6a2f22; }
  .pill.busy {
    color: var(--accent); border-color: var(--accent);
    animation: agentPulse 1.2s ease-in-out infinite;
  }
  @keyframes agentPulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(61,214,198,0.35); }
    50% { opacity: 0.88; box-shadow: 0 0 10px 2px rgba(61,214,198,0.45); }
  }
  #agentThought {
    font-size: 0.8rem; color: var(--muted); margin: 0.25rem 0 0;
    min-height: 1.1em; font-style: italic;
  }
  main {
    display: grid; grid-template-columns: 1.4fr 1fr; gap: 1rem;
    padding: 1rem; max-width: 1400px; margin: 0 auto;
  }
  @media (max-width: 960px) { main { grid-template-columns: 1fr; } }
  section {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 0.9rem 1rem; min-height: 220px;
  }
  section h2 { margin: 0 0 0.75rem; font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .viewport-wrap {
    position: relative; width: 100%; aspect-ratio: 16/9; background: #05070a;
    border-radius: 8px; border: 1px solid var(--line); overflow: hidden;
  }
  #viewport {
    width: 100%; height: 100%; object-fit: contain; display: block; background: #05070a;
  }
  #viewportPlaceholder {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    color: var(--muted); font-size: 0.9rem; pointer-events: none; text-align: center; padding: 1rem;
  }
  #viewportPlaceholder.hidden { display: none; }
  .row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }
  button, input, select {
    background: #0f141c; color: var(--text); border: 1px solid var(--line);
    border-radius: 6px; padding: 0.45rem 0.7rem; font: inherit;
  }
  button { cursor: pointer; }
  button.primary { background: #163a36; border-color: #2a6b62; color: var(--accent); }
  button:hover { filter: brightness(1.08); }
  #log, #actors, #chatLog {
    font-family: ui-monospace, Consolas, monospace; font-size: 0.78rem;
    max-height: 320px; overflow: auto; white-space: pre-wrap; color: #c9d6e8;
  }
  #chatLog { max-height: 240px; margin-bottom: 0.75rem; border: 1px solid var(--line); border-radius: 8px; padding: 0.6rem; background: #0a0e13; }
  #assetButtons button { font-size: 0.75rem; padding: 0.25rem 0.5rem; }
  .chat-row { display: flex; gap: 0.5rem; }
  #chatInput { flex: 1; min-height: 72px; resize: vertical; }
  .actor { padding: 0.25rem 0; border-bottom: 1px solid #1c2530; color: var(--muted); cursor: pointer; }
  .actor.selected { color: var(--accent); font-weight: 600; }
  .hint { color: var(--muted); font-size: 0.8rem; margin-top: 0.5rem; }
  /* Avatar form selector */
  .avatar-form-selector {
    display: flex; gap: 4px; margin-left: auto; padding-left: 1rem;
  }
  .form-btn {
    width: 28px; height: 28px;
    border-radius: 4px;
    border: 1px solid var(--line);
    background: transparent;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.2s;
    font-size: 12px;
    color: var(--muted);
  }
  .form-btn:hover { border-color: var(--accent); background: #163a36; color: var(--accent); }
  .form-btn.active { border-color: var(--accent); background: #163a36; color: var(--accent); }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  }
  #toast {
    position: fixed; bottom: 1rem; right: 1rem; max-width: 360px;
    padding: 0.65rem 0.9rem; border-radius: 8px; border: 1px solid var(--line);
    background: #1a2330; color: var(--text); font-size: 0.85rem; z-index: 99;
    opacity: 0; pointer-events: none; transition: opacity 0.2s;
  }
  #toast.show { opacity: 1; }
  #toast.err { border-color: #6a2f22; color: #ffb4a8; }
  #toast.ok { border-color: #2f5d3a; color: #9dffc0; }
</style>
</head>
<body>
<header>
  <div class="avatar-wrap"><canvas id="avatar" width="96" height="96"></canvas></div>
  <h1>HEPHAESTUS · Mission Control</h1>
  <span id="status" class="pill bad">API offline</span>
  <span class="pill" id="plannerStatus">Planner …</span>
  <span class="pill" id="agentStatus">Agent idle</span>
  <span class="pill" id="apiLabel"></span>
</header>
<section id="preflightPanel" style="max-width:1400px;margin:0 auto;padding:0 1rem 0.5rem">
  <h2 style="font-size:0.85rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin:0 0 0.5rem">Preflight</h2>
  <div id="preflightChecks" class="row" style="gap:0.4rem"></div>
  <p id="preflightHint" class="hint" style="margin:0.25rem 0 0"></p>
</section>
<main>
  <section>
    <h2>Viewport</h2>
    <div class="row">
      <button class="primary" id="btnCapture">Capture frame</button>
      <button id="btnRefresh">Refresh image</button>
      <button id="btnHealth">Ping API</button>
      <button id="btnAgentLoop" class="primary">Run agent loop (Nemotron Ultra)</button>
    </div>
    <div class="viewport-wrap">
      <img id="viewport" alt=""/>
      <div id="viewportPlaceholder">No frame yet — click Capture frame while PIE is running</div>
    </div>
    <p class="hint">Uses GET /v1/frame after vision.capture_frame. Start Play (PIE) in Unreal first.</p>
  </section>
  <section>
    <h2>World commands</h2>
    <div class="row">
      <button class="primary" id="btnSpawnLight">Spawn PointLight</button>
      <button id="btnSpawnCube">Spawn Cube</button>
      <button id="btnList">List actors</button>
    </div>
    <div class="row">
      <input id="actorPath" placeholder="selected actor path" style="flex:1;min-width:180px"/>
      <button id="btnDestroy">Destroy</button>
      <button id="btnPlayIdle">Play idle</button>
      <button id="btnPlayWalk">Play walk</button>
      <button id="btnPlayRun">Play run</button>
      <button id="btnFrameActor">Frame actor</button>
    </div>
    <h2 style="margin-top:1rem">Outliner</h2>
    <div id="actors"></div>
  </section>
  <section style="grid-column: 1 / -1">
    <h2>Hephaestus</h2>
    <div id="chatLog"></div>
    <p id="agentThought"></p>
    <div id="assetButtons" class="row" style="flex-wrap:wrap;margin:0.5rem 0"></div>
    <div class="chat-row">
      <textarea id="chatInput" placeholder="Describe what you want in UE — e.g. Seed a lit scene with three cubes in front of the camera"></textarea>
      <div style="display:flex;flex-direction:column;gap:0.5rem">
        <label class="hint" for="chatMode">Mode</label>
        <select id="chatMode">
          <option value="auto">Auto</option>
          <option value="cinematic">Cinematic</option>
          <option value="gameplay">Gameplay</option>
        </select>
        <button class="primary" id="btnChatSend">Send</button>
        <button id="btnChatReset">New session</button>
        <button id="btnExportSession">Export session</button>
      </div>
    </div>
    <p class="hint">Nemotron-3 Ultra operates UE until your goal is met (or reports what's blocking). Set HEPHAESTUS_PLANNER_VISION=1 for viewport captions. Requires NVIDIA_API_KEY on the forge process.</p>
  </section>
  <section style="grid-column: 1 / -1">
    <h2>Command log</h2>
    <div id="log"></div>
  </section>
</main>
<div id="toast" role="status" aria-live="polite"></div>
<script>
// =======================
// Polymorphic Avatar System (shared with launcher)
// =======================
const canvas = document.getElementById('avatar');
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;
const CX = W / 2, CY = H / 2;

const FORMS = [
  { id: 'geometric', label: 'Geometric', char: '◆' },
  { id: 'organic', label: 'Organic', char: '◉' },
  { id: 'abstract', label: 'Abstract', char: '⬢' },
  { id: 'particle', label: 'Swarm', char: '⋆' }
];

let currentForm = 0;
let targetForm = 0;
let morphProgress = 0;
let state = 'idle';
let time = 0;
let particles = [];
let formShapes = [];
let avatarEventSource = null;

const STATE_COLORS = {
  idle: { primary: '#3dd6c6', secondary: '#06b6d4', glow: '#22d3ee' },
  connecting: { primary: '#f0a202', secondary: '#fbbf24', glow: '#fde047' },
  active: { primary: '#6bcb77', secondary: '#86efac', glow: '#86efac' },
  thinking: { primary: '#a855f7', secondary: '#d946ef', glow: '#f0abfc' },
  working: { primary: '#3dd6c6', secondary: '#06b6d4', glow: '#22d3ee' },
  success: { primary: '#6bcb77', secondary: '#4ade80', glow: '#86efac' },
  error: { primary: '#e4572e', secondary: '#f87171', glow: '#fecaca' }
};

function generateShapes(formId, count) {
  const shapes = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    const radius = 35 + Math.random() * 20;
    const phase = Math.random() * Math.PI * 2;
    const speed = 0.3 + Math.random() * 0.7;
    const size = 3 + Math.random() * 5;
    shapes.push({ angle, radius, phase, speed, size, form: formId });
  }
  return shapes;
}

function initParticles() {
  particles = [];
  for (let i = 0; i < 60; i++) {
    particles.push({
      x: CX + (Math.random() - 0.5) * 80,
      y: CY + (Math.random() - 0.5) * 80,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      size: 1 + Math.random() * 2.5,
      life: Math.random(),
      decay: 0.003 + Math.random() * 0.007,
      hue: 190 + Math.random() * 40
    });
  }
}

function lerp(a, b, t) { return a + (b - a) * t; }
function easeInOutCubic(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
function getStateColors() { return STATE_COLORS[state] || STATE_COLORS.idle; }

function drawGeometricShape(ctx, shape, colors, progress) {
  const a = shape.angle + time * shape.speed * 0.5;
  const r = shape.radius + Math.sin(time * shape.speed + shape.phase) * 8;
  const x = CX + Math.cos(a) * r;
  const y = CY + Math.sin(a) * r;
  const s = shape.size * (1 + 0.3 * Math.sin(time * 2 + shape.phase));

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(a + time * 0.3);

  const sides = 4 + Math.floor(progress * 4);
  ctx.beginPath();
  for (let i = 0; i < sides; i++) {
    const aa = (i / sides) * Math.PI * 2;
    const rr = s * (0.7 + 0.3 * Math.sin(time * 3 + aa * 2));
    ctx.lineTo(Math.cos(aa) * rr, Math.sin(aa) * rr);
  }
  ctx.closePath();

  const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, s * 1.5);
  grad.addColorStop(0, colors.primary);
  grad.addColorStop(1, colors.secondary);
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.strokeStyle = colors.glow;
  ctx.lineWidth = 1.5;
  ctx.shadowColor = colors.glow;
  ctx.shadowBlur = 8;
  ctx.stroke();
  ctx.restore();
}

function drawOrganicShape(ctx, shape, colors, progress) {
  const a = shape.angle + time * shape.speed * 0.3;
  const r = shape.radius + Math.sin(time * shape.speed * 0.7 + shape.phase) * 12;
  const x = CX + Math.cos(a) * r;
  const y = CY + Math.sin(a) * r;
  const s = shape.size * (1 + 0.4 * Math.sin(time * 1.5 + shape.phase));

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(a);

  ctx.beginPath();
  const lobes = 3 + Math.floor(progress * 4);
  for (let i = 0; i < lobes * 2; i++) {
    const aa = (i / (lobes * 2)) * Math.PI * 2;
    const rr = s * (i % 2 === 0 ? 1 : 0.5 + 0.3 * Math.sin(time * 2 + aa * 3));
    ctx.lineTo(Math.cos(aa) * rr, Math.sin(aa) * rr);
  }
  ctx.closePath();

  const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, s * 2);
  grad.addColorStop(0, colors.primary + 'CC');
  grad.addColorStop(0.5, colors.secondary + '88');
  grad.addColorStop(1, 'transparent');
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.strokeStyle = colors.glow;
  ctx.lineWidth = 1;
  ctx.shadowColor = colors.glow;
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.restore();
}

function drawAbstractShape(ctx, shape, colors, progress) {
  const a = shape.angle + time * shape.speed * 0.4;
  const r = shape.radius + Math.sin(time * shape.speed * 0.5 + shape.phase) * 6;
  const x = CX + Math.cos(a) * r;
  const y = CY + Math.sin(a) * r;
  const s = shape.size * (1 + 0.2 * Math.sin(time * 2.5 + shape.phase));

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(a + time * 0.2);

  ctx.beginPath();
  const sides = 6;
  for (let i = 0; i < sides; i++) {
    const aa = (i / sides) * Math.PI * 2;
    const rr = s * (0.8 + 0.4 * Math.sin(time * 4 + aa * 3 + progress * Math.PI));
    ctx.lineTo(Math.cos(aa) * rr, Math.sin(aa) * rr);
  }
  ctx.closePath();

  const grad = ctx.createLinearGradient(-s, -s, s, s);
  grad.addColorStop(0, colors.primary);
  grad.addColorStop(1, colors.secondary);
  ctx.fillStyle = grad;
  ctx.globalAlpha = 0.7 + 0.3 * Math.sin(time * 2 + shape.phase);
  ctx.fill();
  ctx.strokeStyle = colors.glow;
  ctx.lineWidth = 1;
  ctx.shadowColor = colors.glow;
  ctx.shadowBlur = 6;
  ctx.stroke();
  ctx.restore();
}

function renderShapes(colors, formProgress) {
  const drawFns = {
    geometric: drawGeometricShape,
    organic: drawOrganicShape,
    abstract: drawAbstractShape,
    particle: () => {}
  };
  const curShapes = formShapes[currentForm];
  const curDraw = drawFns[FORMS[currentForm].id];
  curShapes.forEach(s => curDraw(ctx, s, colors, formProgress));

  if (targetForm !== currentForm && morphProgress > 0) {
    const tgtShapes = formShapes[targetForm];
    const tgtDraw = drawFns[FORMS[targetForm].id];
    const mp = easeInOutCubic(morphProgress);
    const maxLen = Math.max(curShapes.length, tgtShapes.length);
    for (let i = 0; i < maxLen; i++) {
      const s1 = curShapes[i % curShapes.length];
      const s2 = tgtShapes[i % tgtShapes.length];
      const merged = {
        angle: lerp(s1.angle, s2.angle, mp),
        radius: lerp(s1.radius, s2.radius, mp),
        phase: lerp(s1.phase, s2.phase, mp),
        speed: lerp(s1.speed, s2.speed, mp),
        size: lerp(s1.size, s2.size, mp),
      };
      tgtDraw(ctx, merged, colors, mp);
    }
  }
}

function renderParticles(colors) {
  particles.forEach(p => {
    const dx = CX - p.x, dy = CY - p.y;
    const dist = Math.hypot(dx, dy);
    if (dist > 1) { p.vx += dx * 0.0003; p.vy += dy * 0.0003; }
    p.vx *= 0.985; p.vy *= 0.985;
    p.x += p.vx; p.y += p.vy;
    p.life -= p.decay;
    if (p.life <= 0 || dist > 120) {
      const angle = Math.random() * Math.PI * 2;
      const r = 60 + Math.random() * 40;
      p.x = CX + Math.cos(angle) * r;
      p.y = CY + Math.sin(angle) * r;
      p.life = 1;
      p.vx = (Math.random() - 0.5) * 0.5;
      p.vy = (Math.random() - 0.5) * 0.5;
    }
    const alpha = Math.max(0, Math.min(1, p.life * 1.5));
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fillStyle = `hsla(${p.hue}, 80%, 60%, ${alpha * 0.6})`;
    ctx.shadowColor = colors.glow;
    ctx.shadowBlur = 4;
    ctx.fill();
  });
}

function renderCore(colors) {
  const pulse = 0.6 + 0.4 * Math.sin(time * 3);
  const coreSize = 18 * pulse;
  const grad = ctx.createRadialGradient(CX, CY, 0, CX, CY, coreSize * 2);
  grad.addColorStop(0, colors.primary);
  grad.addColorStop(0.5, colors.secondary + '88');
  grad.addColorStop(1, 'transparent');
  ctx.beginPath();
  ctx.arc(CX, CY, coreSize, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.shadowColor = colors.glow;
  ctx.shadowBlur = 20 * pulse;
  ctx.fill();
}

function renderRing(colors) {
  const ringRadius = 55 + 5 * Math.sin(time * 0.8);
  ctx.beginPath();
  ctx.arc(CX, CY, ringRadius, 0, Math.PI * 2);
  ctx.strokeStyle = colors.glow + '44';
  ctx.lineWidth = 1;
  ctx.shadowColor = colors.glow;
  ctx.shadowBlur = 8;
  ctx.stroke();
  for (let i = 0; i < 3; i++) {
    const a = time * 0.7 + i * Math.PI * 2 / 3;
    const x = CX + Math.cos(a) * ringRadius;
    const y = CY + Math.sin(a) * ringRadius;
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fillStyle = colors.glow;
    ctx.shadowColor = colors.glow;
    ctx.shadowBlur = 6;
    ctx.fill();
  }
}

function render() {
  ctx.clearRect(0, 0, W, H);
  time += 1/60;
  if (targetForm !== currentForm) {
    morphProgress = Math.min(1, morphProgress + 0.02);
    if (morphProgress >= 1) { currentForm = targetForm; morphProgress = 0; }
  } else {
    morphProgress = Math.max(0, morphProgress - 0.02);
  }
  const colors = getStateColors();
  const formProgress = Math.min(1, time * 0.5);
  if (state === 'particle' || FORMS[currentForm].id === 'particle') {
    renderParticles(colors);
    renderCore(colors);
  } else {
    renderShapes(colors, formProgress);
    renderCore(colors);
    renderRing(colors);
  }
  if (state === 'thinking' || state === 'working') {
    const t = Math.sin(time * 5) * 0.5 + 0.5;
    ctx.beginPath();
    ctx.arc(CX, CY, 50 + t * 8, 0, Math.PI * 2);
    ctx.strokeStyle = colors.glow + Math.floor(t * 100).toString(16).padStart(2, '0');
    ctx.lineWidth = 2;
    ctx.shadowBlur = 0;
    ctx.stroke();
  }
  if (state === 'success') {
    const burst = Math.sin(time * 10) * 0.5 + 0.5;
    ctx.beginPath();
    ctx.arc(CX, CY, 40 + burst * 20, 0, Math.PI * 2);
    ctx.strokeStyle = colors.glow + Math.floor(burst * 150).toString(16).padStart(2, '0');
    ctx.lineWidth = 3;
    ctx.stroke();
  }
  if (state === 'error') {
    const shake = Math.sin(time * 30) * 2;
    ctx.translate(shake, 0);
  }
  requestAnimationFrame(render);
}

function initAvatar() {
  formShapes = FORMS.map(f => generateShapes(f.id, 12));
  initParticles();
  connectAvatarSSE();
  requestAnimationFrame(render);
}

function connectAvatarSSE() {
  if (avatarEventSource) avatarEventSource.close();
  avatarEventSource = new EventSource("/api/avatar/stream");
  avatarEventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.state) state = data.state;
      if (typeof data.form === 'number') targetForm = data.form;
    } catch (e) {}
  };
  avatarEventSource.onerror = () => {
    setTimeout(connectAvatarSSE, 3000);
  };
}

async function pollAvatarState() {
  try {
    const res = await fetch("/api/avatar/state");
    const data = await res.json();
    if (data.state) state = data.state;
    if (typeof data.form === 'number') targetForm = data.form;
  } catch {}
  setTimeout(pollAvatarState, 800);
}

initAvatar();
pollAvatarState();

// =======================
// Mission Control Logic
// =======================
const API = "__API_BASE__";
const statusEl = document.getElementById("status");
const plannerStatusEl = document.getElementById("plannerStatus");
const logEl = document.getElementById("log");
const actorsEl = document.getElementById("actors");
const viewport = document.getElementById("viewport");
const viewportPlaceholder = document.getElementById("viewportPlaceholder");
document.getElementById("apiLabel").textContent = API || (location.origin + " → UE :8765");

async function spawnAssetDirect(assetPath) {
  if (!assetPath || agentBusy) return;
  setAgentBusy(true, "Spawning asset…");
  state = "working";
  try {
    const res = await fetch("/agent/spawn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_path: assetPath }),
    });
    const json = await res.json();
    log("spawn", json);
    await showFrame();
    await listPaths();
    state = json.ok ? "success" : "error";
  } catch (e) {
    log("error", String(e));
    state = "error";
  } finally {
    setAgentBusy(false);
  }
}

function renderAssetButtons(paths) {
  const el = document.getElementById("assetButtons");
  if (!el) return;
  el.innerHTML = "";
  for (const p of (paths || []).slice(0, 8)) {
    const b = document.createElement("button");
    b.textContent = "Spawn " + p.split("/").pop();
    b.title = p;
    b.onclick = () => spawnAssetDirect(p);
    el.appendChild(b);
  }
}

async function searchAssets(query) {
  if (!query) return;
  try {
    const res = await fetch("/agent/search?q=" + encodeURIComponent(query));
    const json = await res.json();
    if (json.assets && json.assets.length) {
      renderAssetButtons(json.assets);
      log("assets", json.assets);
    }
  } catch (e) {
    log("error", String(e));
  }
}

function log(msg, data) {
  const line = typeof data === "undefined" ? msg : msg + " " + JSON.stringify(data, null, 0);
  logEl.textContent = new Date().toLocaleTimeString() + "  " + line + "\n" + logEl.textContent;
}

let toastTimer = null;
function showToast(message, kind) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.className = "show" + (kind ? " " + kind : "");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ""; }, 4500);
}

let frameObjectUrl = null;
async function showFrame() {
  const url = API + "/v1/frame?t=" + Date.now();
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) { throw new Error("HTTP " + res.status); }
    const blob = await res.blob();
    if (frameObjectUrl) URL.revokeObjectURL(frameObjectUrl);
    frameObjectUrl = URL.createObjectURL(blob);
    viewport.onload = () => {
      viewportPlaceholder.classList.add("hidden");
      log("frame loaded", { bytes: blob.size, type: blob.type });
    };
    viewport.onerror = () => {
      viewportPlaceholder.classList.remove("hidden");
      viewportPlaceholder.textContent = "Frame blob failed to display";
      log("frame display failed");
    };
    viewport.src = frameObjectUrl;
  } catch (e) {
    viewportPlaceholder.classList.remove("hidden");
    viewportPlaceholder.textContent = "No frame yet — click Capture frame while PIE is running";
    log("frame load failed", String(e));
  }
}

async function postCommand(body) {
  try {
    const res = await fetch(API + "/v1/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    log(body.command, json);
    return json;
  } catch (e) {
    log(body.command + " failed", String(e));
    return { success: false, error: String(e) };
  }
}

async function ping() {
  try {
    const res = await fetch(API + "/v1/health");
    const json = await res.json();
    statusEl.textContent = json.ok ? "API online" : "API error";
    statusEl.className = "pill " + (json.ok ? "ok" : "bad");
    log("health", json);
  } catch (e) {
    statusEl.textContent = "API offline";
    statusEl.className = "pill bad";
    log("health failed", String(e));
  }
}

function spawnPayload(command, extra) {
  return {
    command,
    params: Object.assign({
      transform: {
        location: { x: 0, y: 0, z: 200 },
        rotation: { pitch: 0, yaw: 0, roll: 0 },
        scale: { x: 1, y: 1, z: 1 },
      },
    }, extra || {}),
  };
}

document.getElementById("btnHealth").onclick = ping;
document.getElementById("btnCapture").onclick = async () => {
  viewportPlaceholder.classList.remove("hidden");
  viewportPlaceholder.textContent = "Capturing…";
  const r = await postCommand({ command: "vision.capture_frame", params: {} });
  if (r && r.success) { await showFrame(); }
  else { viewportPlaceholder.textContent = "Capture failed — is PIE running?"; }
};
document.getElementById("btnRefresh").onclick = () => showFrame();
document.getElementById("btnSpawnLight").onclick = () =>
  postCommand(spawnPayload("world.spawn_actor", { class_path: "/Script/Engine.PointLight" }));
document.getElementById("btnSpawnCube").onclick = () =>
  postCommand(spawnPayload("world.spawn_mesh", { mesh_path: "/Engine/BasicShapes/Cube.Cube" }));
document.getElementById("btnList").onclick = async () => {
  const r = await postCommand({ command: "world.list_actors", params: {} });
  let paths = r.actor_paths || [];
  try { const inner = JSON.parse(r.result_json || "{}"); if (inner.actors) paths = inner.actors; } catch (_) {}
  actorsEl.innerHTML = paths.map(p => `<div class="actor">${p}</div>`).join("") || "<div class='actor'>(empty)</div>";
};
document.getElementById("btnDestroy").onclick = () => {
  const path = document.getElementById("actorPath").value.trim();
  if (!path) return;
  postCommand({ command: "world.destroy_actor", params: { actor_path: path } });
};
async function playLocomotionOnSelected(mode) {
  const path = document.getElementById("actorPath").value.trim();
  if (!path) { showToast("Select an actor in the outliner first"); return; }
  const r = await postCommand({
    command: "animation.play_locomotion",
    params: { actor_path: path, mode, loop: true },
  });
  showToast(r.success ? `Playing ${mode}` : (r.error || "Locomotion failed"));
  if (r.success) await listPaths();
}
document.getElementById("btnPlayIdle").onclick = () => playLocomotionOnSelected("idle");
document.getElementById("btnPlayWalk").onclick = () => playLocomotionOnSelected("walk");
document.getElementById("btnPlayRun").onclick = () => playLocomotionOnSelected("run");
async function frameSelectedActor() {
  const path = document.getElementById("actorPath").value.trim();
  if (!path) { showToast("Select an actor in the outliner first"); return; }
  const detail = await postCommand({ command: "world.get_actor", params: { actor_path: path } });
  let loc = { x: 0, y: 0, z: 200 };
  try {
    const inner = JSON.parse(detail.result_json || "{}");
    if (inner.location) loc = inner.location;
  } catch (_) {}
  const r = await postCommand({
    command: "sequence.create_shot",
    params: {
      location: { x: loc.x - 280, y: loc.y + 120, z: loc.z + 90 },
      rotation: { pitch: -12, yaw: 25, roll: 0 },
      duration: 2.5,
    },
  });
  showToast(r.success ? "Framing shot on actor" : (r.error || "Shot failed"));
}
document.getElementById("btnFrameActor").onclick = () => frameSelectedActor();

function countWorld(paths) {
  let lights = 0, meshes = 0;
  for (const p of paths) {
    if (/PointLight|SpotLight|RectLight/.test(p)) lights++;
    if (/StaticMeshActor/.test(p)) meshes++;
  }
  return { lights, meshes };
}

function decide(paths) {
  const { lights, meshes } = countWorld(paths);
  const x = Math.floor(Math.random() * 401) - 200;
  const y = Math.floor(Math.random() * 401) - 200;
  if (lights < 1) {
    return {
      kind: "spawn_light",
      reason: `No lights yet (meshes=${meshes}). Seed a PointLight.`,
      body: spawnPayload("world.spawn_actor", { class_path: "/Script/Engine.PointLight", transform: {
        location: { x, y, z: 280 }, rotation: { pitch: 0, yaw: 0, roll: 0 }, scale: { x: 1, y: 1, z: 1 },
      }}),
    };
  }
  if (meshes < 3) {
    return {
      kind: "spawn_cube",
      reason: `lights=${lights} meshes=${meshes}. Seed/add a cube.`,
      body: spawnPayload("world.spawn_mesh", { mesh_path: "/Engine/BasicShapes/Cube.Cube", transform: {
        location: { x, y, z: 100 }, rotation: { pitch: 0, yaw: 0, roll: 0 }, scale: { x: 1, y: 1, z: 1 },
      }}),
    };
  }
  return { kind: "noop", reason: `Seeded (lights=${lights}, meshes=${meshes}). Holding.`, body: null };
}

async function listPaths() {
  const r = await postCommand({ command: "world.list_actors", params: {} });
  let paths = r.actor_paths || [];
  try { const inner = JSON.parse(r.result_json || "{}"); if (inner.actors) paths = inner.actors; } catch (_) {}
  actorsEl.innerHTML = paths.map(p => {
    const skel = /SkeletalMeshActor|Character|SimAgent/.test(p);
    const label = (skel ? "🦴 " : "") + p;
    return `<div class="actor" data-path="${p.replace(/"/g, '&quot;')}" title="Click to select — destroy, animate, or frame">${label}</div>`;
  }).join("") || "<div class='actor'>(empty)</div>";
  const selected = document.getElementById("actorPath").value.trim();
  actorsEl.querySelectorAll(".actor[data-path]").forEach(el => {
    const path = el.getAttribute("data-path") || "";
    if (path === selected) el.classList.add("selected");
    el.onclick = () => {
      document.getElementById("actorPath").value = path;
      actorsEl.querySelectorAll(".actor.selected").forEach(a => a.classList.remove("selected"));
      el.classList.add("selected");
    };
    el.oncontextmenu = (ev) => {
      ev.preventDefault();
      document.getElementById("actorPath").value = path;
      actorsEl.querySelectorAll(".actor.selected").forEach(a => a.classList.remove("selected"));
      el.classList.add("selected");
      const menu = [
        { label: "Play idle", fn: () => playLocomotionOnSelected("idle") },
        { label: "Play walk", fn: () => playLocomotionOnSelected("walk") },
        { label: "Frame", fn: () => frameSelectedActor() },
        { label: "Destroy", fn: () => postCommand({ command: "world.destroy_actor", params: { actor_path: path } }) },
      ];
      const pick = window.prompt("Actor action: idle | walk | frame | destroy", "idle");
      const action = (pick || "").toLowerCase();
      const hit = menu.find(m => m.label.toLowerCase().includes(action));
      if (hit) hit.fn();
    };
  });
  return paths;
}

let agentBusy = false;
const agentStatusEl = document.getElementById("agentStatus");
const agentThoughtEl = document.getElementById("agentThought");
let thoughtStream = null;

function setAgentBusy(busy, label) {
  agentBusy = !!busy;
  if (agentStatusEl) {
    agentStatusEl.textContent = busy ? (label || "Agent working…") : "Agent idle";
    agentStatusEl.className = busy ? "pill busy" : "pill";
  }
  if (!busy && agentThoughtEl) agentThoughtEl.textContent = "";
}

function connectThoughtStream() {
  if (thoughtStream) return;
  thoughtStream = new EventSource("/agent/thoughts/stream");
  fetch("/agent/thoughts/last").then((r) => r.json()).then((t) => {
    if (t && t.metadata && t.metadata.busy) setAgentBusy(true, "Agent working…");
    if (t && t.kind !== "status" && t.content && agentThoughtEl) {
      agentThoughtEl.textContent = String(t.content).slice(0, 240);
    }
  }).catch(() => {});
  thoughtStream.onmessage = (ev) => {
    try {
      const t = JSON.parse(ev.data);
      if (t.metadata && typeof t.metadata.busy === "boolean") {
        setAgentBusy(t.metadata.busy || t.busy, t.metadata.busy ? "Agent working…" : undefined);
      } else if (t.busy) {
        setAgentBusy(true, "Agent working…");
      }
      if (t.kind === "status") return;
      if (t.content) {
        if (agentThoughtEl) agentThoughtEl.textContent = String(t.content).slice(0, 240);
        const avatarState = (t.kind === "plan" || t.kind === "llm") ? "thinking" : "working";
        if (agentBusy) state = avatarState;
        log(t.kind || "thought", t.content);
      }
    } catch (_) {}
  };
  thoughtStream.onerror = () => {
    if (thoughtStream) { thoughtStream.close(); thoughtStream = null; }
    setTimeout(connectThoughtStream, 3000);
  };
}
connectThoughtStream();

async function pollAgentJob(jobId) {
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    const res = await fetch("/agent/job/" + encodeURIComponent(jobId));
    const data = await res.json();
    if (data.status === "done" && data.result) return data.result;
    if (data.status === "error") throw new Error(data.error || "Agent job failed");
    await new Promise((r) => setTimeout(r, 350));
  }
  throw new Error("Agent job timed out");
}

function applyChatResult(json) {
  log("chat", json.reply || json.error || json);
  if (json.grade) log("reflection", json.grade.summary || json.grade);
  if (json.asset_matches && json.asset_matches.length) {
    renderAssetButtons(json.asset_matches);
    log("assets", json.asset_matches);
  }
  if (json.llm_error) {
    log("error", "LLM: " + json.llm_error);
    showToast("LLM: " + json.llm_error, "err");
  }
  if (!json.llm_available && json.planner === "heuristic") {
    showToast("Heuristic mode — set NVIDIA_API_KEY for Nemotron Ultra", "err");
  }
  if (json.session) renderChat(json.session.messages || []);
  state = json.ok ? "success" : "active";
}

function applyLoopResult(json) {
  log("tool_result", json);
  if (json.llm_error) log("error", "LLM: " + json.llm_error);
  if (!json.llm_available) log("error", "NIM planner not used — check NVIDIA_API_KEY in shell running forge observe");
  (json.thoughts || []).forEach((t) => log(t.kind || "plan", t.content || ""));
  state = json.ok ? "success" : "error";
  setTimeout(() => { state = "active"; }, 1500);
  log("reflection", json.planner ? ("Finished with planner " + json.planner) : "Finished");
}

function renderChat(messages) {
  const el = document.getElementById("chatLog");
  if (!el) return;
  el.innerHTML = "";
  for (const m of messages || []) {
    const div = document.createElement("div");
    div.style.whiteSpace = "pre-wrap";
    div.textContent = (m.role === "user" ? "You: " : "Hephaestus: ") + (m.content || "");
    el.appendChild(div);
  }
  el.scrollTop = el.scrollHeight;
}

async function loadAgentHealth() {
  if (!plannerStatusEl) return;
  try {
    const res = await fetch("/agent/health");
    const data = await res.json();
    const checksEl = document.getElementById("preflightChecks");
    const hintEl = document.getElementById("preflightHint");
    if (checksEl && data.checks) {
      checksEl.innerHTML = "";
      for (const c of data.checks) {
        const span = document.createElement("span");
        span.className = "pill " + (c.ok ? "ok" : "bad");
        span.title = c.detail || "";
        span.textContent = (c.ok ? "✓ " : "✗ ") + c.name;
        checksEl.appendChild(span);
      }
    }
    if (hintEl) {
      hintEl.textContent = data.ready_for_goals
        ? "Ready for agent goals."
        : (data.checks || []).filter(c => !c.ok && c.blocker).map(c => c.detail).join(" ") || "Fix blockers above before chatting.";
    }
    if (data.llm_available) {
      plannerStatusEl.textContent = "Nemotron Ultra ready";
      plannerStatusEl.className = "pill ok";
    } else {
      plannerStatusEl.textContent = "No API key";
      plannerStatusEl.className = "pill bad";
      if (data.llm_error) log("error", data.llm_error);
    }
    const statusEl = document.getElementById("status");
    if (statusEl) {
      const ueCheck = (data.checks || []).find(c => c.name === "ue_pie");
      if (ueCheck && ueCheck.ok) {
        statusEl.textContent = "PIE online";
        statusEl.className = "pill ok";
      } else {
        statusEl.textContent = "PIE offline";
        statusEl.className = "pill bad";
      }
    }
  } catch {
    plannerStatusEl.textContent = "Planner offline";
    plannerStatusEl.className = "pill bad";
  }
}

async function loadSession() {
  try {
    const res = await fetch("/agent/session");
    const data = await res.json();
    if (data.session) {
      renderChat(data.session.messages || []);
      const modeEl = document.getElementById("chatMode");
      if (modeEl && data.session.mode) modeEl.value = data.session.mode;
    }
  } catch {}
}

async function sendChat(reset) {
  if (agentBusy) return;
  const input = document.getElementById("chatInput");
  const message = (input && input.value || "").trim();
  if (!message && !reset) return;
  setAgentBusy(true, "Hephaestus working…");
  const btn = document.getElementById("btnChatSend");
  if (btn) btn.disabled = true;
  state = "working";
  try {
    const modeEl = document.getElementById("chatMode");
    const mode = modeEl ? modeEl.value : "auto";
    const res = await fetch("/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message || "Start fresh", reset: !!reset, max_steps: 20, mode }),
    });
    let json = await res.json();
    if (json.job_id) {
      log("plan", "Job " + json.job_id + " — streaming thoughts…");
      json = await pollAgentJob(json.job_id);
    }
    applyChatResult(json);
    if (input && !reset) input.value = "";
    await showFrame();
    await listPaths();
  } catch (e) {
    log("error", String(e));
    showToast(String(e), "err");
    state = "error";
  } finally {
    setAgentBusy(false);
    if (btn) btn.disabled = false;
  }
}

document.getElementById("btnChatSend").onclick = () => sendChat(false);
document.getElementById("btnChatReset").onclick = () => sendChat(true);
document.getElementById("btnExportSession").onclick = async () => {
  try {
    const res = await fetch("/agent/export");
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "hephaestus-session-" + (data.session && data.session.id ? data.session.id : "export") + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
    showToast("Session exported", "ok");
  } catch (e) {
    showToast("Export failed: " + e, "err");
  }
};
document.getElementById("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(false); }
});
document.getElementById("chatInput").addEventListener("blur", () => {
  const q = document.getElementById("chatInput").value.trim();
  if (q && q.length < 40) searchAssets(q);
});
loadSession();
loadAgentHealth();
setInterval(loadAgentHealth, 30000);

document.getElementById("btnAgentLoop").onclick = async () => {
  if (agentBusy) return;
  setAgentBusy(true, "Agent loop running…");
  const btn = document.getElementById("btnAgentLoop");
  btn.disabled = true;
  try {
    log("plan", "Starting Nemotron Ultra agent loop via /agent/loop");
    viewportPlaceholder.classList.remove("hidden");
    viewportPlaceholder.textContent = "Agent running (Nemotron Ultra)…";
    state = 'working';
    const chatInput = document.getElementById("chatInput");
    const goalText = (chatInput && chatInput.value.trim()) || "Seed a lit test scene with a few cubes in front of the camera, then idle.";
    const res = await fetch("/agent/loop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        max_steps: 12,
        goal: goalText,
      }),
    });
    let json = await res.json();
    if (json.job_id) {
      log("plan", "Loop job " + json.job_id + " — streaming thoughts…");
      json = await pollAgentJob(json.job_id);
    }
    applyLoopResult(json);
    await showFrame();
    await listPaths();
  } catch (e) {
    state = 'error';
    setTimeout(() => { state = 'idle'; }, 1000);
    log("error", String(e));
  } finally {
    setAgentBusy(false);
    btn.disabled = false;
  }
};

ping();
setInterval(ping, 5000);
showFrame();
</script>
</body>
</html>
"""


@app.command("search-assets")
def search_assets_cmd(
    query: Annotated[str, typer.Argument(help="Search token e.g. dog, cube")],
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
):
    """Search /Game (and engine basics) for meshes matching query."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from agent_asset import search_project_assets
    from ue_agent_loop import RemoteUeClient

    client = RemoteUeClient(f"http://{host}:{port}", timeout=30.0)
    seen: list[str] = []
    for cls in ("", "SkeletalMesh", "StaticMesh", "AnimSequence"):
        for p in search_project_assets(client, query, asset_class=cls, limit=12):
            if p not in seen:
                seen.append(p)
    for p in seen:
        console.print(p)
    if not seen:
        console.print("[yellow]No matches[/yellow]")
        raise typer.Exit(1)


@app.command("spawn-asset")
def spawn_asset_cmd(
    asset_path: Annotated[str, typer.Argument(help="/Game/... mesh or skeletal asset path")],
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
    no_light: Annotated[bool, typer.Option("--no-light", help="Skip spawning a point light")] = False,
):
    """Spawn a project asset in front of the PIE camera (no LLM)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from agent_asset import spawn_asset_in_view
    from ue_agent_loop import RemoteUeClient

    client = RemoteUeClient(f"http://{host}:{port}", timeout=60.0)
    try:
        client.health()
    except Exception as exc:
        console.print(f"[red]✗ Remote API unreachable: {exc}[/red]")
        raise typer.Exit(1)
    results = spawn_asset_in_view(client, asset_path, with_light=not no_light)
    for i, res in enumerate(results, 1):
        console.print(f"[dim]step {i}[/dim] success={res.get('success')} error={res.get('error')}")
    if results and all(r.get("success") for r in results):
        console.print(f"[green]✓ Spawned {asset_path}[/green]")
    else:
        console.print(f"[red]✗ Spawn failed for {asset_path}[/red]")
        raise typer.Exit(2)


@app.command("command")
def command_cmd(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root (optional)")] = None,
    command: Annotated[Optional[str], typer.Option("--command", "-c", help="Command name, e.g. world.spawn_actor")] = "world.spawn_actor",
    class_path: Annotated[str, typer.Option("--class", help="Actor class for spawn")] = "/Script/Engine.PointLight",
    mesh_path: Annotated[str, typer.Option("--mesh", help="Static mesh path for spawn_mesh")] = "/Engine/BasicShapes/Cube.Cube",
    actor_path: Annotated[str, typer.Option("--actor", help="Actor path for destroy")] = "",
    x: Annotated[float, typer.Option("--x")] = 0.0,
    y: Annotated[float, typer.Option("--y")] = 0.0,
    z: Annotated[float, typer.Option("--z")] = 200.0,
    json_body: Annotated[Optional[str], typer.Option("--json", help="Raw command JSON (overrides builders)")] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
    timeout: Annotated[float, typer.Option("--timeout")] = 30.0,
):
    """
    POST a command to the Hephaestus Remote API inside a running PIE session.

    Requires: UE editor with Play (PIE) active so the Remote API is listening.
    """
    import urllib.error
    import urllib.request

    sys.path.insert(0, str(Path(__file__).resolve().parent / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"))
    from hephaestus import commands as hcmd

    if json_body:
        payload = json_body
    elif command == "world.spawn_actor":
        payload = hcmd.spawn_actor_json(class_path=class_path, location=(x, y, z))
    elif command == "world.spawn_mesh":
        payload = hcmd.spawn_mesh_json(mesh_path=mesh_path, location=(x, y, z))
    elif command == "world.destroy_actor":
        if not actor_path:
            console.print("[red]✗ --actor required for world.destroy_actor[/red]")
            raise typer.Exit(1)
        payload = hcmd.destroy_actor_json(actor_path)
    elif command == "world.list_actors":
        payload = hcmd.list_actors_json(class_path if class_path != "/Script/Engine.PointLight" else "")
    elif command == "vision.capture_frame":
        payload = hcmd.capture_frame_json()
    else:
        payload = json.dumps({"command": command, "params": {}})

    url = f"http://{host}:{port}/v1/command"
    console.print(f"[dim]POST {url}[/dim]")
    console.print(f"[dim]{payload}[/dim]")

    req = urllib.request.Request(
        url,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            console.print(body)
            try:
                parsed = json.loads(body)
                if not parsed.get("success", False):
                    raise typer.Exit(2)
            except json.JSONDecodeError:
                pass
    except urllib.error.URLError as exc:
        console.print(f"[red]✗ Remote API unreachable: {exc}[/red]")
        console.print("[yellow]Start Play (PIE) in UE first. Look for: HephaestusRemoteApi: listening on http://127.0.0.1:8765[/yellow]")
        raise typer.Exit(1)


@app.command("loop")
def agent_loop_cmd(
    steps: Annotated[int, typer.Option("--steps", "-n", help="Max observe->act cycles")] = 20,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
    seed: Annotated[Optional[int], typer.Option("--seed", help="RNG seed for spawn positions")] = None,
    timeout: Annotated[float, typer.Option("--timeout")] = 60.0,
    planner: Annotated[str, typer.Option("--planner", help="heuristic | llm | auto")] = "auto",
    goal: Annotated[str, typer.Option("--goal", help="Natural-language goal for the LLM planner")] = (
        "Seed a lit test scene with a few cubes visible in frame, then idle."
    ),
    llm_model: Annotated[Optional[str], typer.Option("--llm-model", help="Chat model id")] = (
        "nvidia/nemotron-3-ultra-550b-a55b"
    ),
    llm_url: Annotated[Optional[str], typer.Option("--llm-url", help="OpenAI-compatible base URL")] = (
        "https://integrate.api.nvidia.com/v1"
    ),
):
    """
    Run an observe -> decide -> act -> recapture loop against a live PIE session.

    Default planner LLM is Nemotron-3 Ultra (nvidia/nemotron-3-ultra-550b-a55b) via NVIDIA NIM.
    Requires NVIDIA_API_KEY. --planner auto uses NIM when a key is available, else heuristic.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ue_agent_loop import ObserveActLoop, RemoteUeClient
    from ue_vision_planner import VisionLLMPlanner, resolve_planner_mode

    mode = resolve_planner_mode(planner)
    base = f"http://{host}:{port}"
    client = RemoteUeClient(base, timeout=max(timeout, 120.0))
    from agent_asset import augment_goal_with_assets

    goal, asset_matches, _asset_meta = augment_goal_with_assets(client, goal)

    llm = VisionLLMPlanner(
        base_url=llm_url,
        model=llm_model,
        goal=goal,
        asset_hints=asset_matches,
        fallback_rng=__import__("random").Random(seed),
        timeout=max(timeout, 120.0),
    )
    use_llm = mode == "llm" or (mode == "auto" and llm.available)
    if mode == "llm" and not llm.available:
        console.print(
            "[red]✗ --planner llm requires NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY "
            "(Nemotron-3 via NIM), or a local --llm-url[/red]"
        )
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold]Observe -> Act loop[/bold]\n"
        f"API: [cyan]{base}[/cyan]\n"
        f"Steps: [cyan]{steps}[/cyan]\n"
        f"Planner: [cyan]{'nim/' + llm.model if use_llm else 'heuristic'}[/cyan]",
        border_style="green",
    ))
    if use_llm:
        console.print(f"[dim]LLM: {llm.base_url}  model={llm.model}[/dim]")
        console.print(f"[dim]Goal: {goal}[/dim]")
        if "nvidia.com" in llm.base_url and not (
            os.environ.get("NVIDIA_API_KEY") or os.environ.get("HEPHAESTUS_LLM_API_KEY")
        ):
            console.print(
                "[yellow]Warning: NIM URL set but NVIDIA_API_KEY missing — "
                "requests will fail over to heuristic unless a key is provided.[/yellow]"
            )

    def on_thought(kind: str, content: str, metadata: dict) -> None:
        color = {
            "observation": "cyan",
            "plan": "yellow",
            "action": "magenta",
            "tool_result": "green",
            "error": "red",
            "reflection": "blue",
        }.get(kind, "white")
        # Avoid non-ASCII + Rich markup collisions from LLM text like [llm/...]
        safe = content.replace("\u2192", "->").replace("[", "(").replace("]", ")")
        console.print(f"[{color}]{kind}:[/{color}] {safe}")

    try:
        health = client.health()
        plugin_v = health.get("plugin_version", "")
        if plugin_v:
            console.print(f"[dim]health: ok — plugin {plugin_v}[/dim]")
        else:
            console.print(f"[dim]health: {health}[/dim]")
    except Exception as exc:
        console.print(f"[red]✗ Remote API unreachable: {exc}[/red]")
        console.print("[yellow]Start Play (PIE) in UE first.[/yellow]")
        raise typer.Exit(1)

    loop = ObserveActLoop(
        client=client,
        seed=seed,
        on_thought=on_thought,
        planner=(llm.decide if use_llm else None),
        goal=goal,
        asset_hints=asset_matches,
    )
    step_budget = max(steps, 16) if asset_matches else steps
    results, grade = loop.run_until_goal(max_steps=step_budget)
    if use_llm and llm.last_error:
        console.print(f"[yellow]Last LLM error (fallback may have been used): {llm.last_error}[/yellow]")
    failed = [r for r in results if not r.ok]
    console.print(
        f"[bold]{'Goal met' if grade.met else 'Stopped'}[/bold]: {grade.summary} — "
        f"{len(results)} step(s), lights={results[-1].reobservation.lights if results else 0} "
        f"meshes={results[-1].reobservation.meshes if results else 0}"
    )
    if failed or not grade.met:
        raise typer.Exit(2)


@app.command("smoke-spawn")
def smoke_spawn(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    class_path: Annotated[str, typer.Option("--class", help="Actor class path")] = "/Script/Engine.PointLight",
    x: Annotated[float, typer.Option("--x")] = 0.0,
    y: Annotated[float, typer.Option("--y")] = 0.0,
    z: Annotated[float, typer.Option("--z")] = 200.0,
):
    """
    Print a world.spawn_actor smoke-test recipe for the UE Python console (PIE required).
    """
    project_root = project_path or Path.cwd()
    plugin_py = project_root / "Plugins" / "HephaestusBridge" / "Content" / "Python"
    smoke_script = plugin_py / "hephaestus" / "smoke_spawn_actor.py"

    # Keep builder importable without Unreal
    sys.path.insert(0, str(Path(__file__).resolve().parent / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"))
    try:
        from hephaestus.commands import build_spawn_actor_command, spawn_actor_json
    except Exception as exc:
        console.print(f"[red]✗ Could not import command builder: {exc}[/red]")
        raise typer.Exit(1)

    payload = build_spawn_actor_command(class_path=class_path, location=(x, y, z))
    py_snippet = (
        f"import sys; sys.path.insert(0, r'{plugin_py}')\n"
        f"import hephaestus.commands as hc\n"
        f"print(hc.execute_command({json.dumps(payload)}))"
    )
    console.print("[bold green]world.spawn_actor smoke test[/bold green]")
    console.print("1. Open the project in UE 5.8")
    console.print("2. Press Play (PIE) - GameInstance subsystems only exist in PIE")
    console.print("3. Output Log -> Python, paste:")
    console.print(py_snippet)
    console.print(f"\nOr run: {smoke_script}")
    console.print(f"\nJSON: {spawn_actor_json(class_path=class_path, location=(x, y, z))}")


@app.command()
def evolve(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    skill: Annotated[Optional[str], typer.Option("--skill", "-s", help="Skill name to hot-patch")] = None,
    file: Annotated[Optional[Path], typer.Option("--file", "-f", help="Python/C++ snippet file to inject")] = None,
):
    """
    Hot-patch agent skills at runtime.

    Recompiles plugin and hot-reloads in editor without session loss.
    """
    project_root = project_path or Path.cwd()
    forge_dir = project_root / ".hephaestus_forge"
    
    if not forge_dir.exists():
        console.print(f"[red]✗ Not a Hephaestus project: {project_root}[/red]")
        raise typer.Exit(1)
    
    if not skill and not file:
        console.print("[red]✗ Must specify --skill or --file[/red]")
        raise typer.Exit(1)
    
    console.print(Panel.fit(
        f"[bold]Evolving Agent Skills[/bold]\n"
        f"Skill: [cyan]{skill or 'N/A'}[/cyan]\n"
        f"File: [cyan]{file or 'N/A'}[/cyan]",
        border_style="yellow",
    ))
    
    # Load skill manifest
    manifest_path = forge_dir / "skill_manifest.json"
    if not manifest_path.exists():
        console.print("[red]✗ skill_manifest.json not found[/red]")
        raise typer.Exit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    console.print("[red]✗ forge evolve is not implemented in v1.0 (experimental)[/red]")
    console.print("[dim]Use forge sync-plugin + UE rebuild for bridge changes.[/dim]")
    raise typer.Exit(1)


@app.command("nim-parallel")
def nim_parallel(
    task: Annotated[str, typer.Option("--task", "-t", help="Coding task for dual Nemotron")],
    context_file: Annotated[
        Optional[Path],
        typer.Option("--context", "-c", help="Optional file/dir notes to attach"),
    ] = None,
    out: Annotated[
        Optional[Path],
        typer.Option("--out", "-o", help="Write merged markdown here"),
    ] = None,
):
    """
    Run Nemotron-3 Ultra and Nemotron-3.5 Lightning in parallel on one coding task.

    Ultra returns architecture/plan; Lightning returns an implementation draft.
    Requires NVIDIA_API_KEY.
    """
    if not (os.environ.get("NVIDIA_API_KEY") or os.environ.get("HEPHAESTUS_LLM_API_KEY")):
        console.print("[red]✗ Set NVIDIA_API_KEY (or HEPHAESTUS_LLM_API_KEY)[/red]")
        raise typer.Exit(1)

    try:
        from hephaestus_forge.cloud.parallel_nim import ParallelNemotronCoder
        from hephaestus_forge.cloud.nim_client import (
            DEFAULT_FAST_MODEL,
            DEFAULT_PLANNER_MODEL,
        )
    except ImportError:
        from cloud.parallel_nim import ParallelNemotronCoder
        from cloud.nim_client import DEFAULT_FAST_MODEL, DEFAULT_PLANNER_MODEL

    context = ""
    if context_file and context_file.exists():
        if context_file.is_file():
            context = context_file.read_text(encoding="utf-8", errors="replace")[:12000]
        else:
            context = f"(directory) {context_file}"

    console.print(Panel.fit(
        f"[bold]Parallel Nemotron coding[/bold]\n"
        f"Planner: [cyan]{DEFAULT_PLANNER_MODEL}[/cyan]\n"
        f"Lightning: [cyan]{DEFAULT_FAST_MODEL}[/cyan]\n"
        f"Task: {task[:200]}",
        border_style="blue",
    ))

    coder = ParallelNemotronCoder()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        progress.add_task("Calling Ultra + Lightning concurrently...", total=None)
        result = coder.run_sync(task, context=context)

    if result.ultra_error:
        console.print(f"[yellow]Ultra error:[/yellow] {result.ultra_error}")
    if result.lightning_error:
        console.print(f"[yellow]Lightning error:[/yellow] {result.lightning_error}")
    if not result.ok:
        console.print("[red]✗ Both models failed[/red]")
        raise typer.Exit(1)

    console.print(result.merged_markdown)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.merged_markdown, encoding="utf-8")
        console.print(f"[green]✓ Wrote[/green] {out}")


@app.command("gpu-dev")
def gpu_dev(
    repo: Annotated[Optional[Path], typer.Option("--repo", "-r", help="Hephaestus repo root")] = None,
    task: Annotated[Optional[str], typer.Option("--task", "-t", help="Coding task for the GPU agent")] = None,
    download: Annotated[bool, typer.Option("--download/--no-download", help="Download coding model if missing")] = True,
    serve_only: Annotated[bool, typer.Option("--serve-only", help="Start LLM server only, no agent task")] = False,
    apply: Annotated[bool, typer.Option("--apply/--no-apply", help="Apply file edits from agent response")] = False,
    host: Annotated[str, typer.Option("--host", help="LLM bind host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="LLM port")] = 8080,
):
    """
    GPU dev mode — run a coding LLM on the local/cloud GPU (no UE required).

    Starts llama.cpp server with Qwen2.5-Coder-7B, optionally runs a dev task.
    """
    try:
        from hephaestus_forge.gpu_dev.llama_manager import LlamaServerManager
        from hephaestus_forge.gpu_dev.dev_agent import DevAgent
    except ImportError:
        from gpu_dev.llama_manager import LlamaServerManager
        from gpu_dev.dev_agent import DevAgent

    repo_root = (repo or Path.cwd()).resolve()
    models_dir = repo_root / "Agent_Runtime" / "models"
    mgr = LlamaServerManager(models_dir=models_dir, host=host, port=port)

    scan = scanner.scan()
    console.print(f"[cyan]GPU:[/cyan] {mgr.nvidia_smi_summary()}")

    if download:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            progress.add_task("Downloading Qwen2.5-Coder-7B Q4_K_M (~4.5GB)...", total=None)
            model_path = mgr.ensure_model()
        console.print(f"[green]✓ Model ready:[/green] {model_path}")
    else:
        model_path = mgr.default_model_path()

    console.print("[cyan]Starting llama.cpp server on GPU...[/cyan]")
    mgr.start(model_path)
    console.print(f"[green]✓ LLM server:[/green] http://{host}:{port}/v1")

    if serve_only:
        console.print("[dim]Serve-only mode. Ctrl+C to stop.[/dim]")
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            mgr.stop()
        return

    if not task:
        task = (
            "Review hephaestus_forge/forge.py deploy() and implement starting the vision_stack "
            "FastAPI service from Agent_Runtime/vision_stack/vision_processor.py when enabled in config."
        )

    agent = DevAgent(base_url=mgr.base_url, repo_root=repo_root)
    console.print(Panel.fit(f"[bold]GPU Dev Task[/bold]\n{task}", border_style="blue"))
    response, edits = agent.run_task(task, apply=apply)
    console.print(response)
    if edits:
        console.print(f"[green]Edits {'applied' if apply else 'detected'}:[/green] {', '.join(edits)}")
    else:
        console.print("[yellow]No file edits parsed — response is advisory only[/yellow]")

    if not serve_only:
        mgr.stop()


@app.command("gpu-train")
def gpu_train(
    repo: Annotated[Optional[Path], typer.Option("--repo", "-r", help="Hephaestus repo root")] = None,
    mode: Annotated[str, typer.Option("--mode", "-m", help="lora | embed")] = "lora",
    max_steps: Annotated[int, typer.Option("--max-steps", help="LoRA training steps (keep low for $ budget)")] = 60,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output directory")] = None,
):
    """
    GPU training on Hephaestus codebase — QLoRA fine-tune or code embeddings.

    LoRA: ~30-45 min on L40S, teaches the model Hephaestus code patterns.
    Embed: builds a RAG index from source files (fast, ~5 min).
    """
    try:
        from hephaestus_forge.gpu_dev.dataset_builder import build_code_dataset
        from hephaestus_forge.gpu_dev.trainer import train_lora, embed_codebase
    except ImportError:
        from gpu_dev.dataset_builder import build_code_dataset
        from gpu_dev.trainer import train_lora, embed_codebase

    repo_root = (repo or Path.cwd()).resolve()
    out_base = output or (repo_root / "Agent_Runtime" / "training")
    out_base.mkdir(parents=True, exist_ok=True)

    scan = scanner.scan()
    if not scan.gpus:
        console.print("[red]✗ No GPU detected — training requires CUDA[/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold]GPU Training[/bold]\n"
        f"Mode: [cyan]{mode}[/cyan]\n"
        f"GPU: [cyan]{scan.gpus[0].name}[/cyan] ({scan.total_vram_mb} MB)\n"
        f"Repo: [cyan]{repo_root}[/cyan]",
        border_style="magenta",
    ))

    dataset_path = out_base / "hephaestus_code.jsonl"
    n = build_code_dataset(repo_root, dataset_path)
    console.print(f"[green]✓ Dataset:[/green] {n} examples -> {dataset_path}")

    if mode == "embed":
        index_dir = embed_codebase(repo_root, out_base / "embeddings")
        console.print(f"[green]✓ Embeddings saved:[/green] {index_dir}")
        return

    if mode != "lora":
        console.print(f"[red]Unknown mode: {mode}[/red]")
        raise typer.Exit(1)

    console.print("[cyan]Installing training deps if needed...[/cyan]")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "torch", "transformers", "peft", "trl", "datasets", "accelerate",
    ])

    try:
        adapter_dir = train_lora(
            dataset_path=dataset_path,
            output_dir=out_base / "lora",
            max_steps=max_steps,
        )
    except Exception as e:
        console.print(f"[red]LoRA training failed: {e}[/red]")
        console.print("[yellow]Use --mode embed (works on Brev) or forge gpu-dev for inference.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]✓ LoRA adapter saved:[/green] {adapter_dir}")
    console.print(
        "[dim]Use the adapter with transformers+peft for inference, or merge and export to GGUF later.[/dim]"
    )


@app.command("agent-run")
def agent_run(
    repo: Annotated[Optional[Path], typer.Option("--repo", "-r", help="Hephaestus repo root")] = None,
    config: Annotated[Optional[Path], typer.Option("--config", "-c", help="cloud_agent.yaml path")] = None,
    queue: Annotated[Optional[Path], typer.Option("--queue", "-q", help="Override task queue yaml")] = None,
):
    """
    Autonomous offline worker — run on Brev, stop instance when queue finishes.

    Use before powering off your PC:
      bash hephaestus_forge/scripts/go_offline.sh ~/Hephaestus

    Edits and logs land in Agent_Runtime/autonomous/. Brev stops automatically
    when done so you do not burn $/hr idle.
    """
    try:
        from hephaestus_forge.cloud.agent_runner import load_agent_config, run_autonomous
    except ImportError:
        from cloud.agent_runner import load_agent_config, run_autonomous

    repo_root = (repo or Path.cwd()).resolve()
    cfg_path = config or (Path(__file__).resolve().parent / "forge_config" / "cloud_agent.yaml")
    if queue:
        merged = load_agent_config(cfg_path)
        with queue.open(encoding="utf-8") as f:
            merged["tasks"] = (yaml.safe_load(f) or {}).get("tasks", [])
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "heph_agent_queue.yaml"
        tmp.write_text(yaml.dump(merged, sort_keys=False), encoding="utf-8")
        cfg_path = tmp

    console.print(Panel.fit(
        f"[bold]Autonomous Hephaestus Worker[/bold]\n"
        f"Repo: [cyan]{repo_root}[/cyan]\n"
        f"Config: [cyan]{cfg_path}[/cyan]\n"
        f"[dim]Stops Brev when queue completes — no idle burn[/dim]",
        border_style="green",
    ))
    raise typer.Exit(run_autonomous(repo_root, cfg_path))


@app.command()
def scan(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
):
    """
    Re-run system scan and display results.
    """
    scan = scanner.scan()
    if verbose:
        console.print_json(scan.model_dump_json(indent=2))


@app.command()
def cloud(
    # Provider selection
    provider: Annotated[str, typer.Option("--provider", "-p", help="brev | nim | bitdeer | runpod | auto")] = "brev",

    # Instance config
    instance: Annotated[str, typer.Option("--instance", "-i", help="Instance type (l40s, h100-80gb, …)")] = "l40s",
    gpus: Annotated[int, typer.Option("--gpus", "-g", help="Number of GPUs")] = 1,
    spot: Annotated[bool, typer.Option("--spot/--no-spot", help="Use spot/preemptible instances")] = True,
    hourly_rate: Annotated[Optional[float], typer.Option("--hourly-rate", help="Override $/hr from Brev create page")] = None,

    # Session config — HARD DEFAULT $15
    hours: Annotated[Optional[float], typer.Option("--hours", "-t", help="Max session hours (auto-capped by $15)")] = None,
    budget: Annotated[float, typer.Option("--budget", "-b", help="Session budget USD (clamped to <=$15)")] = 15.0,

    # Workload
    task: Annotated[Optional[str], typer.Option("--task", help="Task description for auto-routing")] = None,
    auto_route: Annotated[bool, typer.Option("--auto-route/--no-auto-route", help="Auto-select provider based on task")] = False,

    # Deployment
    deploy: Annotated[bool, typer.Option("--deploy/--no-deploy", help="Run setup after launch")] = True,
    detach: Annotated[bool, typer.Option("--detach", "-d", help="Return after launch; watchdog still stops on budget")] = False,
    stop_all: Annotated[bool, typer.Option("--stop-all", help="Emergency: brev stop --all and exit")] = False,

    # Project
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root")] = None,
):
    """
    Launch cloud GPU with a hard $15 spend ceiling (Brev credits-safe).

    Safety layers:
      1. Budget clamped to <= $15 (absolute hard ceiling in code)
      2. Max hours = budget * 0.92 / hourly_rate
      3. Watchdog stops Brev instance before budget is exhausted
      4. No payment method + Brev credits = platform also won't overcharge

    Examples:
        forge cloud --provider brev --instance l40s --budget 15
        forge cloud --provider brev --hourly-rate 1.50 --budget 15
        forge cloud --stop-all
        forge cloud --provider nim --task "quick material variants"
    """
    if not CLOUD_AVAILABLE:
        console.print("[red]✗ Cloud modules not available. Check imports.[/red]")
        raise typer.Exit(1)

    HARD_MAX = 15.0
    if budget > HARD_MAX:
        console.print(f"[yellow]Budget ${budget:.2f} clamped to ${HARD_MAX:.2f}[/yellow]")
        budget = HARD_MAX
    if budget <= 0:
        console.print("[red]✗ Budget must be > 0[/red]")
        raise typer.Exit(1)

    project_root = project_path or Path.cwd()
    forge_dir = project_root / ".hephaestus_forge"
    config_path = forge_dir / "config.yaml"

    if not forge_dir.exists():
        console.print(f"[red]✗ Not a Hephaestus project: {project_root}[/red]")
        raise typer.Exit(1)

    cloud_yaml = forge_dir / "cloud.yaml"
    cfg = _load_cloud_cfg(cloud_yaml if cloud_yaml.exists() else config_path, config_path)

    # Ensure config.yaml has cloud section for BudgetManager
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not raw.get("cloud"):
        raw["cloud"] = cfg.get("cloud", {})
        config_path.write_text(yaml.dump(raw, sort_keys=False), encoding="utf-8")

    budget_mgr = BudgetManager(config_path)

    if stop_all:
        client = BrevClient(budget_mgr)
        client.stop_all()
        raise typer.Exit(0)

    status = budget_mgr.get_status()
    console.print(Panel.fit(
        f"[bold]Budget Status (hard ceiling ${status.get('hard_ceiling', HARD_MAX):.2f})[/bold]\n"
        f"Monthly: ${status['monthly']['spent']:.2f} / ${status['monthly']['limit']:.2f} ({status['monthly']['pct_used']:.1f}%)\n"
        f"Remaining: ${status['monthly']['remaining']:.2f}",
        border_style="blue" if status["monthly"]["remaining"] > 0 else "red",
    ))

    if status["monthly"]["remaining"] <= 0:
        console.print("[red]✗ Budget exhausted under $15 hard ceiling. Cannot launch.[/red]")
        raise typer.Exit(1)

    session_id = f"heph-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        session = budget_mgr.start_session(session_id, budget)
    except BudgetExceededError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Session started: {session_id} (Budget: ${session.limit_usd:.2f})[/green]")

    if auto_route and task:
        provider, instance, gpus, spot = _route_task(task, budget_mgr, cfg)
        console.print(f"[cyan]Auto-routed: {provider} {instance} x{gpus}[/cyan]")

    if provider == "nim":
        asyncio.run(_run_nim_session(task, budget_mgr, cfg))
    elif provider == "brev":
        asyncio.run(_run_brev_session(
            instance=instance,
            hours=hours,
            hourly_rate=hourly_rate,
            deploy=deploy,
            detach=detach,
            budget_mgr=budget_mgr,
            cfg=cfg,
            project_root=project_root,
        ))
    elif provider == "bitdeer":
        h = hours or 1.0
        if not budget_mgr.can_afford(provider, instance, h, spot):
            console.print(f"[red]✗ Cannot afford {provider} {instance} under $15 ceiling[/red]")
            raise typer.Exit(1)
        asyncio.run(_run_bitdeer_session(instance, gpus, h, spot, deploy, detach, budget_mgr, cfg, project_root))
    elif provider == "runpod":
        console.print("[yellow]RunPod provider not yet implemented — use brev[/yellow]")
        raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)


def _load_cloud_cfg(cloud_yaml: Path, config_path: Path) -> dict:
    cfg: dict = {}
    if cloud_yaml.exists():
        with open(cloud_yaml, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    if not cfg.get("cloud") and config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    cloud = cfg.setdefault("cloud", {})
    budget = cloud.setdefault("budget", {})
    budget.setdefault("hard_ceiling_usd", 15)
    budget.setdefault("monthly_limit_usd", 15)
    budget.setdefault("per_session_limit_usd", 15)
    budget.setdefault("auto_stop_at_limit", True)
    return cfg


def _route_task(task: str, budget_mgr: BudgetManager, cfg: dict) -> tuple[str, str, int, bool]:
    """Route task to optimal provider based on complexity and budget."""
    routing = cfg.get("cloud", {}).get("routing", {}).get("rules", [])

    task_lower = task.lower()
    complexity = 0.5
    context_needed = 8192

    if any(kw in task_lower for kw in ["full game", "vertical slice", "multiplayer", "architecture", "refactor"]):
        complexity = 0.9
        context_needed = 128000
    elif any(kw in task_lower for kw in ["system", "pipeline", "combat", "ai", "procedural"]):
        complexity = 0.7
        context_needed = 32768
    elif any(kw in task_lower for kw in ["material", "shader", "texture", "variant"]):
        complexity = 0.3
    elif any(kw in task_lower for kw in ["embedding", "embed", "search", "rag"]):
        complexity = 0.1

    for rule in routing:
        cond = rule["condition"]
        try:
            if eval(
                cond.replace("task.complexity", str(complexity))
                .replace("context", str(context_needed))
                .replace("task.type", '"inference"')
            ):
                target = rule["target"]
                parts = target.split(":")
                provider = parts[0]
                inst = parts[1] if len(parts) > 1 else "l40s"
                if provider == "local":
                    continue
                if budget_mgr.can_afford(provider, inst, 1.0):
                    return provider, inst, 1, True
        except Exception:
            continue

    return "brev", "l40s", 1, True


async def _run_brev_session(
    instance: str,
    hours: Optional[float],
    hourly_rate: Optional[float],
    deploy: bool,
    detach: bool,
    budget_mgr: BudgetManager,
    cfg: dict,
    project_root: Path,
):
    """Launch Brev L40S (or configured GPU) with watchdog auto-stop <= $15."""
    brev_cfg = next((p for p in cfg.get("cloud", {}).get("providers", []) if p["name"] == "brev"), None)
    if not brev_cfg:
        console.print("[red]✗ brev provider missing from cloud config[/red]")
        raise typer.Exit(1)

    conf = brev_cfg.get("config", {})
    rate = hourly_rate or float(conf.get("default_hourly_rate", 1.50))
    types = conf.get("instance_types", {})
    if instance in types:
        rate = hourly_rate or float(types[instance].get("hourly_rate", rate))

    client = BrevClient(
        budget_mgr,
        hard_ceiling_usd=15.0,
        hourly_rate=rate,
        gpu_name=conf.get("gpu_name", "L40S"),
        instance_type=conf.get("instance_type", "gpu-l40s-a.1gpu-32vcpu-128gb"),
    )

    if not BrevClient.brev_available():
        console.print(
            "[red]✗ Brev CLI not installed.[/red]\n"
            "  Docs: https://docs.nvidia.com/brev/getting-started/quickstart\n"
            "  Then: [bold]brev login[/bold]"
        )
        raise typer.Exit(1)

    max_h = client.max_hours_for_budget()
    if hours is not None:
        max_h = min(max_h, hours)
    if max_h < 0.25:
        console.print(f"[red]✗ Not enough budget for a useful session at ${rate:.2f}/hr[/red]")
        raise typer.Exit(1)

    console.print(
        f"[cyan]Plan: <={max_h:.2f}h @ ${rate:.2f}/hr -> max ~${max_h * rate:.2f} "
        f"(stop watchdog at 92% of reserve)[/cyan]"
    )

    startup = _build_cloud_init_script(project_root, deploy) if deploy else None
    try:
        brev_inst = client.launch(max_hours=max_h, startup_script=startup, sort_price=conf.get("sort_by_price", True))
        console.print(Panel.fit(
            f"[bold green]Brev instance running[/bold green]\n"
            f"Name: [cyan]{brev_inst.name}[/cyan]\n"
            f"GPU: [cyan]{brev_inst.gpu_name}[/cyan]\n"
            f"Shell: [bold]brev shell {brev_inst.name}[/bold]\n"
            f"Emergency stop: [bold]forge cloud --stop-all[/bold]",
            border_style="green",
        ))

        if detach:
            console.print("[yellow]Detached — watchdog still armed. Stop with: forge cloud --stop-all[/yellow]")
            return

        console.print("[dim]Watchdog active. Ctrl+C stops instance immediately.[/dim]")
        while client._instance and not client._instance.stopped:
            await asyncio.sleep(5)

    except BudgetExceededError as e:
        console.print(f"[red]Budget error: {e}[/red]")
        client.stop_all()
    except KeyboardInterrupt:
        console.print("\n[yellow]Ctrl+C — stopping Brev instance now[/yellow]")
        client.stop()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        try:
            client.stop()
        except Exception:
            client.stop_all()
    finally:
        if client._instance and not client._instance.stopped:
            client.stop()


async def _run_nim_session(task: str, budget_mgr: BudgetManager, cfg: dict):
    """Run NIM inference session under budget."""
    nim_cfg = next(p for p in cfg["cloud"]["providers"] if p["name"] == "nim")
    nim_client = NIMClient(budget_mgr, base_url=nim_cfg["config"]["base_url"])

    console.print(f"[green]NIM session ready for task: {task}[/green]")

    if task:
        response = await nim_client.chat_completion(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=[{"role": "user", "content": task}],
            max_tokens=512,
        )
        console.print(f"[bold]Response:[/bold] {response}")

    await nim_client.close()


async def _run_bitdeer_session(
    instance_type: str,
    gpus: int,
    hours: float,
    spot: bool,
    deploy: bool,
    detach: bool,
    budget_mgr: BudgetManager,
    cfg: dict,
    project_root: Path,
):
    """Launch Bitdeer instance under $15 ceiling."""
    max_cost = min(15.0, budget_mgr.session.limit_usd if budget_mgr.session else 15.0)
    bitdeer_cfg = next(p for p in cfg["cloud"]["providers"] if p["name"] == "bitdeer")
    client = BitdeerClient(budget_mgr, base_url=bitdeer_cfg["config"]["base_url"])
    client.set_instance_types(bitdeer_cfg["config"]["instance_types"])
    rate = client.estimate_hourly_cost(instance_type, spot)
    if rate > 0:
        hours = min(hours, (max_cost * 0.92) / rate)

    user_data = _build_cloud_init_script(project_root, deploy)

    try:
        instance = await client.launch_instance(
            instance_type=instance_type,
            spot=spot,
            max_hours=hours,
            user_data=user_data,
        )

        console.print(f"[green]Instance launched: {instance.instance_id}[/green]")
        console.print(f"  Rate: ${instance.hourly_rate:.2f}/hr | Max: ${instance.hourly_rate * hours:.2f}")

        if deploy and instance.public_ip:
            console.print("[dim]Waiting for deployment...[/dim]")
            await _wait_for_deployment(instance.public_ip, budget_mgr)

        if not detach:
            await asyncio.sleep(min(hours * 3600, max_cost / max(instance.hourly_rate, 0.01) * 3600 * 0.92))
            await client.terminate_instance(instance.instance_id)

    except BudgetExceededError as e:
        console.print(f"[red]Budget error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        await client.close()


def _build_cloud_init_script(project_root: Path, deploy: bool) -> str:
    """Generate cloud-init script for instance bootstrap."""
    return """#!/bin/bash
set -e
cd /home/ubuntu/workspace 2>/dev/null || cd /workspace || cd ~

echo "HephaestusForge bootstrap — parent forge cloud watchdog will stop this instance <= $15"

command -v docker >/dev/null 2>&1 || curl -fsSL https://get.docker.com | sh || true

if [ -n "${HEPHAESTUS_REPO:-}" ] && [ ! -d "hephaestus" ]; then
  git clone "$HEPHAESTUS_REPO" hephaestus || true
fi

echo "Bootstrap done. Use: brev shell <name>"
"""


async def _wait_for_deployment(ip: str, budget_mgr: BudgetManager, timeout: int = 300):
    """Poll deployment health endpoint."""
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(timeout // 5):
            try:
                resp = await client.get(f"http://{ip}:8012/api/agent/health")
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(5)
    raise TimeoutError("Deployment did not become healthy")


@app.command("version")
def version_cmd():
    """Print HephaestusForge and bridge template versions."""
    try:
        from version import BRIDGE_VERSION, FORGE_VERSION
    except ImportError:
        from hephaestus_forge.version import BRIDGE_VERSION, FORGE_VERSION

    console.print(f"HephaestusForge [cyan]{FORGE_VERSION}[/cyan]")
    console.print(f"HephaestusBridge template [cyan]{BRIDGE_VERSION}[/cyan]")


@app.command()
def health(
    project_path: Annotated[Optional[Path], typer.Argument(help="Adopted UE project root")] = None,
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    json_out: Annotated[bool, typer.Option("--json", help="Emit preflight report as JSON")] = False,
):
    """Preflight check: UE PIE API, NIM key, planner, adopted project."""
    try:
        from preflight_health import run_preflight
    except ImportError:
        from hephaestus_forge.preflight_health import run_preflight

    project_root = project_path
    if project_root is None:
        try:
            try:
                from project_registry import ProjectRegistry
            except ImportError:
                from hephaestus_forge.project_registry import ProjectRegistry

            reg = ProjectRegistry()
            if reg.active_path:
                project_root = Path(reg.active_path)
        except Exception:
            project_root = None

    report = run_preflight(api, project_root)
    if json_out:
        import json as _json

        typer.echo(_json.dumps(report.to_dict(), indent=2))
        raise typer.Exit(0 if report.ready else 1)
    for check in report.checks:
        style = "green" if check.ok else ("yellow" if not check.blocker else "red")
        label = "OK" if check.ok else ("WARN" if not check.blocker else "BLOCKED")
        console.print(f"[{style}]{label}[/] {check.name}: {check.detail}")
    raise typer.Exit(0 if report.ready else 1)


@app.command("e2e")
def e2e_check_cmd(
    project_path: Annotated[Optional[Path], typer.Argument(help="Adopted UE project root")] = None,
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    sync: Annotated[bool, typer.Option("--sync", help="Run forge sync-plugin before checks")] = False,
    offline: Annotated[bool, typer.Option("--offline", help="Skip live PIE command probes")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit E2E report as JSON")] = False,
):
    """Production operator E2E checklist (template sync + optional live PIE probes)."""
    try:
        from e2e_check import run_e2e_check
    except ImportError:
        from hephaestus_forge.e2e_check import run_e2e_check

    project_root = (project_path or Path.cwd()).resolve()
    report = run_e2e_check(project_root, remote_api=api, sync=sync, live=not offline)
    if json_out:
        import json as _json

        typer.echo(_json.dumps(report.to_dict(), indent=2))
        raise typer.Exit(0 if report.ok else 2)
    for step in report.steps:
        style = "green" if step.ok else "red"
        console.print(f"[{style}]{'OK' if step.ok else 'FAIL'}[/] {step.name}: {step.detail}")
    raise typer.Exit(0 if report.ok else 2)


@app.command()
def doctor(
    project_path: Annotated[Optional[Path], typer.Argument(help="Adopted UE project root")] = None,
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    sync: Annotated[bool, typer.Option("--sync", help="Run forge sync-plugin before checks")] = False,
    offline: Annotated[bool, typer.Option("--offline", help="Skip live PIE command probes")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit doctor report as JSON")] = False,
):
    """Operator doctor: rebuild checklist + offline e2e + preflight."""
    try:
        from doctor import run_doctor
    except ImportError:
        from hephaestus_forge.doctor import run_doctor

    project_root = project_path
    if project_root is None:
        try:
            from project_registry import ProjectRegistry

            reg = ProjectRegistry()
            if reg.active_path:
                project_root = Path(reg.active_path)
        except Exception:
            project_root = None
    report = run_doctor(project_root, remote_api=api, sync=sync, live=not offline)
    if json_out:
        import json as _json

        typer.echo(_json.dumps(report.to_dict(), indent=2))
        raise typer.Exit(0 if report.ok else 1)
    console.print("[bold]Rebuild checklist[/bold]")
    for line in report.checklist:
        console.print(f"  • {line}")
    console.print("\n[bold]E2E[/bold]")
    for step in report.e2e.get("steps", []):
        style = "green" if step.get("ok") else "red"
        console.print(f"[{style}]{'OK' if step.get('ok') else 'FAIL'}[/] {step.get('name')}: {step.get('detail')}")
    console.print("\n[bold]Preflight[/bold]")
    for check in report.preflight.get("checks", []):
        style = "green" if check.get("ok") else "yellow"
        console.print(f"[{style}]{check.get('name')}[/]: {check.get('detail')}")
    raise typer.Exit(0 if report.ok else 1)


@app.command("run")
def autonomous_run(
    project_path: Annotated[Path, typer.Argument(help="Adopted UE project root")],
    goal: Annotated[str, typer.Argument(help="Natural-language goal")],
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    max_steps: Annotated[int, typer.Option("--max-steps", help="Max observe-act steps")] = 24,
    repair: Annotated[bool, typer.Option("--repair/--no-repair", help="Run repair loop on grade failure")] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Emit autonomous report as JSON")] = False,
    mode: Annotated[str, typer.Option("--mode", help="auto | cinematic | gameplay")] = "auto",
):
    """Run a single autonomous goal with NIM planner (operator v1)."""
    try:
        from autonomous_runner import run_autonomous_goal
    except ImportError:
        from hephaestus_forge.autonomous_runner import run_autonomous_goal

    report = run_autonomous_goal(
        goal,
        project_root=project_path,
        remote_api=api,
        max_steps=max_steps,
        repair=repair,
        mode=mode if mode in ("cinematic", "gameplay", "auto") else "auto",
        require_nim=True,
    )
    if json_out:
        import json as _json

        typer.echo(_json.dumps(report.to_dict(), indent=2))
        raise typer.Exit(0 if report.ok else 1)
    console.print(f"[bold]Autonomous[/bold] planner={report.planner} ok={report.ok}")
    console.print(report.grade.get("summary", ""))
    if report.llm_error:
        console.print(f"[yellow]llm_error: {report.llm_error}[/yellow]")
    raise typer.Exit(0 if report.ok else 1)


@app.command("autonomous-suite")
def autonomous_suite_cmd(
    project_path: Annotated[Path, typer.Argument(help="Adopted UE project root")],
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    scenario: Annotated[Optional[list[str]], typer.Option("--scenario", help="Run subset (A, B, E1, ...)")] = None,
    offline: Annotated[bool, typer.Option("--offline", help="Skip live NIM autonomous goals")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit suite report as JSON")] = False,
):
    """Run operator A–I autonomous acceptance suite (v1)."""
    try:
        from autonomous_suite import run_autonomous_suite
    except ImportError:
        from hephaestus_forge.autonomous_suite import run_autonomous_suite

    report = run_autonomous_suite(
        project_path,
        remote_api=api,
        scenario_filter=scenario,
        live=not offline,
        skip_nim=offline,
    )
    if json_out:
        import json as _json

        typer.echo(_json.dumps(report.to_dict(), indent=2))
        raise typer.Exit(0 if report.ok else 1)
    skipped = report.skipped_ids
    passed = report.passed_ids
    failed = [s.scenario_id for s in report.steps if not s.ok]
    console.print(
        f"[bold]Autonomous suite {report.milestone}[/bold] ok={report.ok} "
        f"passed={len(passed)} skipped={len(skipped)} failed={len(failed)}"
    )
    for step in report.steps:
        if not step.ok:
            label, style = "FAIL", "red"
        elif (step.report or {}).get("skipped"):
            label, style = "SKIP", "yellow"
        else:
            label, style = "OK", "green"
        console.print(f"[{style}]{label}[/] {step.scenario_id}: {step.detail[:120]}")
    raise typer.Exit(0 if report.ok else 1)


@app.command()
def gate(
    project_path: Annotated[Optional[Path], typer.Argument(help="Adopted UE project root")] = None,
    api: Annotated[str, typer.Option("--api", help="UE Remote API base URL")] = "http://127.0.0.1:8765",
    sync: Annotated[bool, typer.Option("--sync", help="Run forge sync-plugin before checks")] = False,
    offline: Annotated[bool, typer.Option("--offline", help="Skip live PIE command probes")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Emit operator gate report as JSON")] = False,
):
    """Production operator gate (v0.9): doctor + packaging checks."""
    try:
        from operator_gate import run_operator_gate
    except ImportError:
        from hephaestus_forge.operator_gate import run_operator_gate

    project_root = project_path
    if project_root is None:
        try:
            from project_registry import ProjectRegistry

            reg = ProjectRegistry()
            if reg.active_path:
                project_root = Path(reg.active_path)
        except Exception:
            project_root = None
    report = run_operator_gate(
        project_root,
        remote_api=api,
        sync=sync,
        live=not offline,
    )
    if json_out:
        import json as _json

        typer.echo(_json.dumps(report.to_dict(), indent=2))
        raise typer.Exit(0 if report.ok else 1)
    console.print(f"[bold]Operator gate {report.milestone}[/bold] (forge {report.to_dict()['forge_version']})")
    for step in report.steps:
        style = "green" if step.ok else ("yellow" if not step.blocker else "red")
        label = "OK" if step.ok else ("WARN" if not step.blocker else "FAIL")
        console.print(f"[{style}]{label}[/] {step.name}: {step.detail}")
    raise typer.Exit(0 if report.ok else 1)


def app_entry() -> None:
    """Console-script entry: ensure package dir is importable for flat modules."""
    import hephaestus_forge  # noqa: F401 — boots sys.path for sibling modules

    _pkg = str(Path(__file__).resolve().parent)
    if _pkg not in sys.path:
        sys.path.insert(0, _pkg)
    app()


if __name__ == "__main__":
    _pkg = str(Path(__file__).resolve().parent)
    if _pkg not in sys.path:
        sys.path.insert(0, _pkg)
    app()