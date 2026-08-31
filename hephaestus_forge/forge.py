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
    nemotron: dict = Field(default_factory=lambda: {
        "model_id": "nvidia/Nemotron-3-Ultra",
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

    @classmethod
    def from_scan(cls, project_name: str, project_root: Path, scan: SystemScanResult) -> "ForgeConfig":
        paths = PathsConfig(project_root=str(project_root))
        # Load cloud config from template if exists
        cloud_config = CloudConfig()
        return cls(project_name=project_name, system=scan, paths=paths, cloud=cloud_config)

    @classmethod
    def load(cls, config_path: "str | Path") -> "ForgeConfig":
        """Load a project's ``config.yaml`` into a ForgeConfig.

        The pydantic-settings ``yaml_file`` config key is ignored without a
        YamlConfigSettingsSource, so read and validate the YAML explicitly.
        Extra keys (e.g. ``agent_runtime``) are preserved via ``extra="allow"``.
        """
        path = Path(config_path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)


# ──────────────────────────────────────────────────────────────────────────────
# System Scanner
# ──────────────────────────────────────────────────────────────────────────────

class SystemScanner:
    def __init__(self, console: Console):
        self.console = console

    def scan(self) -> SystemScanResult:
        self.console.print("[bold cyan]🔍 Scanning system...[/bold cyan]")

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
            self.console.print("[yellow]⚠ nvidia-smi not found. GPU acceleration unavailable.[/yellow]")

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
        # Check env var first
        if ue_path := os.environ.get("UE_PATH"):
            version_file = Path(ue_path) / "Engine" / "Build" / "Version.txt"
            if version_file.exists():
                version = version_file.read_text().strip()
                if version.startswith("5.8"):
                    return ue_path, version

        # Common locations
        candidates = [
            Path.home() / "UnrealEngine" / "5.8",
            Path("C:/UnrealEngine/5.8"),
            Path("D:/UnrealEngine/5.8"),
            Path("/opt/UnrealEngine/5.8"),
        ]

        for path in candidates:
            if path.exists():
                version_file = path / "Engine" / "Build" / "Version.txt"
                if version_file.exists():
                    version = version_file.read_text().strip()
                    if version.startswith("5.8"):
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

        table.add_row("Platform", "✓", result.platform)
        table.add_row("Python", "✓", f"{result.python_version} ({result.python_executable})")

        ue_status = "✓" if result.ue_path else "✗"
        ue_detail = f"{result.ue_version} at {result.ue_path}" if result.ue_path else "NOT FOUND"
        table.add_row("Unreal Engine 5.8", ue_status, ue_detail)

        blender_status = "✓" if result.blender_path else "✗"
        blender_detail = f"{result.blender_version} at {result.blender_path}" if result.blender_path else "NOT FOUND"
        table.add_row("Blender", blender_status, blender_detail)

        cc5_status = "✓" if result.cc5_path else "✗"
        cc5_detail = result.cc5_path if result.cc5_path else "NOT FOUND (optional)"
        table.add_row("Character Creator 5", cc5_status, cc5_detail)

        if result.gpus:
            for gpu in result.gpus:
                table.add_row(
                    f"GPU {gpu.index}",
                    "✓",
                    f"{gpu.name} | VRAM: {gpu.vram_total_mb}MB total / {gpu.vram_free_mb}MB free | Driver: {gpu.driver_version} | CUDA: {gpu.cuda_version}",
                )
        else:
            table.add_row("GPU", "✗", "No NVIDIA GPU detected")

        table.add_row("Total VRAM", "✓" if result.total_vram_mb > 0 else "✗", f"{result.total_vram_mb} MB")
        table.add_row("Recommended Quant", "✓", result.recommended_quant)
        table.add_row("Vision Resolution", "✓", f"{result.vision_resolution}px")
        table.add_row("TTS Model Size", "✓", result.tts_model_size)

        self.console.print(table)

        if result.warnings:
            self.console.print("\n[bold yellow]⚠ Warnings:[/bold yellow]")
            for w in result.warnings:
                self.console.print(f"  • {w}")


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

        self.console.print("[green]✓ Project scaffold complete[/green]")

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
    configuration: Annotated[str, typer.Option("--configuration", help="Build configuration")] = "Development",
    target_platform: Annotated[Optional[str], typer.Option("--platform", help="Target platform (Win64/Linux/Mac)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the build command without running it")] = False,
):
    """
    Compile the project editor target (builds the HephaestusBridge plugin).

    Locates the project's .uproject (root or a subfolder such as Hephaestus/),
    resolves the UE5.8 engine from config/env, and invokes UnrealBuildTool on
    the '<Project>Editor' target. Use --dry-run to print the exact command.
    """
    from hephaestus_forge.ue_build import (
        build_ubt_command, default_target_platform, editor_target_name,
        find_uproject, resolve_ue_root,
    )

    project_root = (project_path or Path.cwd()).resolve()

    # Locate the .uproject (repo keeps it under Hephaestus/).
    uproject = find_uproject(project_root)
    if not uproject:
        console.print(f"[red]✗ No .uproject found under {project_root}[/red]")
        raise typer.Exit(1)

    # Resolve the engine from config.system.ue_path or the environment.
    cfg = _load_project_config(project_root)
    ue_root = resolve_ue_root((cfg.get("system") or {}).get("ue_path"))

    tp = target_platform or default_target_platform()
    target = editor_target_name(uproject)

    console.print(Panel.fit(
        f"[bold]Compiling {uproject.stem} (editor target)[/bold]\n"
        f"Project: [cyan]{uproject}[/cyan]\n"
        f"Target: [cyan]{target} {tp} {configuration}[/cyan]\n"
        f"UE5.8: [cyan]{ue_root or 'NOT FOUND'}[/cyan]",
        border_style="blue",
    ))

    if not ue_root:
        console.print("[red]✗ UE5.8 engine not found. Set system.ue_path in config.yaml "
                      "or the UE_PATH environment variable.[/red]")
        if not dry_run:
            raise typer.Exit(1)
        console.print("[yellow](dry-run) Using placeholder engine path for command preview.[/yellow]")
        ue_root = Path("C:/Program Files/Epic Games/UE_5.8")

    cmd = build_ubt_command(
        ue_root, uproject, target=target, target_platform=tp,
        configuration=configuration, clean=clean,
    )

    if dry_run:
        console.print("[bold]Build command:[/bold]")
        console.print(f"  [cyan]{' '.join(cmd)}[/cyan]")
        return

    build_script = Path(cmd[0])
    if not build_script.exists():
        console.print(f"[red]✗ Build script not found: {build_script}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Compiling with UnrealBuildTool...", total=None)
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ue_root))
        elapsed = time.time() - start_time

    if result.returncode == 0:
        console.print(f"[green]✓ Compilation successful ({elapsed:.1f}s)[/green]")
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
    nim_model: Annotated[str, typer.Option("--nim-model", help="NIM model to use")] = "nvidia/nemotron-3-ultra",
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
    config = ForgeConfig.load(config_path)
    
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
):
    """
    Open Mission Control Dashboard (React/Three.js/WebGPU).

    Live viewport stream, Chain of Thought log, World Outliner,
    Asset Browser, Voice I/O console.
    """
    project_root = project_path or Path.cwd()
    forge_dir = project_root / ".hephaestus_forge"
    
    if not forge_dir.exists():
        console.print(f"[red]✗ Not a Hephaestus project: {project_root}[/red]")
        raise typer.Exit(1)
    
    # Load config
    config_path = forge_dir / "config.yaml"
    config = ForgeConfig.load(config_path)
    
    dashboard_dir = project_root / config.paths.mission_control_dir
    
    console.print(Panel.fit(
        f"[bold]Mission Control Dashboard[/bold]\n"
        f"Port: [cyan]{port}[/cyan]\n"
        f"Dashboard Source: [cyan]{dashboard_dir}[/cyan]",
        border_style="blue",
    ))
    
    # Check if dashboard is built
    dist_dir = dashboard_dir / "dist"
    if not dist_dir.exists():
        console.print("[yellow]Dashboard not built. Building...[/yellow]")
        
        # Build dashboard
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(dashboard_dir),
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            console.print("[red]✗ Build failed[/red]")
            console.print(result.stderr)
            raise typer.Exit(1)
        
        console.print("[green]✓ Dashboard built[/green]")
    
    # Serve dashboard
    console.print(f"[green]Starting dashboard on http://127.0.0.1:{port}[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    
    try:
        # Use Python's http.server for static files
        import http.server
        import socketserver
        
        class SPAHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(dist_dir), **kwargs)
            
            def do_GET(self):
                # SPA fallback
                if not (dist_dir / self.path.lstrip("/")).exists() and "." not in self.path:
                    self.path = "/index.html"
                return super().do_GET()
        
        with socketserver.TCPServer(("127.0.0.1", port), SPAHandler) as httpd:
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")


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
    
    if file:
        # Inject code snippet
        console.print(f"[dim]Injecting code from {file}[/dim]")
        snippet = file.read_text()
        
        # Determine if Python or C++ based on extension
        if file.suffix == ".py":
            console.print("[green]Python skill injection not yet implemented[/green]")
        elif file.suffix in [".cpp", ".h", ".hpp"]:
            console.print("[green]C++ skill injection not yet implemented[/green]")
        else:
            console.print("[yellow]Unknown file type[/yellow]")
    
    if skill:
        # Update skill manifest
        console.print(f"[dim]Updating skill: {skill}[/dim]")
        # Would modify manifest and regenerate C++ headers
    
    # Recompile
    console.print("[dim]Triggering recompile...[/dim]")
    # Would call compile with hot_reload=True
    
    console.print("[green]✓ Evolution complete (stub)[/green]")


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
            model="nvidia/nemotron-3-8b",
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


def _load_project_config(project_root: Path) -> dict:
    """Load a scaffolded project's config.yaml into a plain dict."""
    config_path = project_root / ".hephaestus_forge" / "config.yaml"
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.command()
def health(
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON")] = False,
    strict: Annotated[bool, typer.Option("--strict", help="Exit non-zero on any warning too")] = False,
    timeout: Annotated[float, typer.Option("--timeout", help="Per-service probe timeout (s)")] = 2.0,
):
    """
    Pre-deploy status check: verifies toolchain, config, models, and services.

    Green means ready; warnings are non-fatal (e.g. a service not started yet);
    a critical failure (missing project/config) exits non-zero.
    """
    from hephaestus_forge.runtime.health import (
        FAIL, OK, WARN, Check, HealthReport, check_file, check_service, check_tool,
    )
    from hephaestus_forge.gpu_dev.llama_manager import LlamaServerManager

    project_root = (project_path or Path.cwd()).resolve()
    cfg = _load_project_config(project_root)
    report = HealthReport()

    # --- Project & config ---
    config_file = project_root / ".hephaestus_forge" / "config.yaml"
    report.add(check_file("project config", config_file, critical=True))

    # --- Toolchain ---
    report.add(check_tool("python", Path(sys.executable).name, critical=True,
                          which=lambda e: sys.executable))
    report.add(check_tool("node", "node"))
    report.add(check_tool("npm", "npm"))
    gpu_check = check_tool("nvidia-smi (GPU)", "nvidia-smi")
    if gpu_check.status == OK:
        gpu_check.detail = LlamaServerManager.nvidia_smi_summary()
    report.add(gpu_check)

    # --- UE engine ---
    ue_path = (cfg.get("system") or {}).get("ue_path")
    if ue_path:
        report.add(check_file("UE5.8 engine", Path(ue_path), warn_only=True))
    else:
        report.add(Check("UE5.8 engine", WARN, "system.ue_path not set (needed for compile/deploy)"))

    # --- Model files (large, gitignored; warn if absent) ---
    runtime_cfg = cfg.get("agent_runtime") or {}
    runtime_dir = project_root / (cfg.get("paths", {}) or {}).get("agent_runtime_dir", "Agent_Runtime")
    for svc in ("llama_server", "tts_server", "vision_stack"):
        model_rel = (runtime_cfg.get(svc) or {}).get("model_path")
        if model_rel:
            report.add(check_file(f"model: {svc}", project_root / model_rel, warn_only=True))

    # --- Services (probed over HTTP; usually down before deploy) ---
    net = cfg.get("network") or {}
    inference = ((cfg.get("models") or {}).get("inference")) or {}
    llama_host = inference.get("host", "127.0.0.1")
    llama_port = inference.get("port", 8080)
    endpoints = [
        ("llama-server", f"http://{llama_host}:{llama_port}/v1/models"),
        ("tts-server", f"http://127.0.0.1:{net.get('tts_port', 8082)}/health"),
        ("vision-stack", f"http://127.0.0.1:{net.get('vision_port', 8083)}/health"),
        ("dcc-bridge", f"http://127.0.0.1:{net.get('dcc_bridge_port', 8084)}/health"),
        ("mission-control", f"http://127.0.0.1:{net.get('dashboard_port', 3000)}/"),
        ("ue-bridge", os.environ.get("HEPHAESTUS_UE_URL", "http://127.0.0.1:8099") + "/health"),
    ]
    for name, url in endpoints:
        report.add(check_service(name, url, timeout=timeout))

    # --- Mission Control build artifact ---
    mc_dir = project_root / (cfg.get("paths", {}) or {}).get("mission_control_dir", "MissionControl")
    report.add(check_file("dashboard build (dist)", mc_dir / "dist", warn_only=True))

    if as_json:
        console.print_json(json.dumps(report.to_dict()))
    else:
        table = Table(title="HephaestusForge Health", show_lines=False)
        table.add_column("Check", style="bold")
        table.add_column("Status")
        table.add_column("Detail", style="dim", overflow="fold")
        style_for = {OK: "[green]OK[/green]", WARN: "[yellow]WARN[/yellow]", FAIL: "[red]FAIL[/red]"}
        for c in report.checks:
            label = style_for.get(c.status, c.status)
            if c.status == FAIL and c.critical:
                label = "[bold red]FAIL*[/bold red]"
            table.add_row(c.name, label, c.detail)
        console.print(table)
        counts = report.counts()
        verdict_color = {OK: "green", WARN: "yellow", FAIL: "red"}[report.overall]
        console.print(Panel.fit(
            f"Overall: [{verdict_color}]{report.overall.upper()}[/{verdict_color}]  "
            f"([green]{counts[OK]} ok[/green], [yellow]{counts[WARN]} warn[/yellow], [red]{counts[FAIL]} fail[/red])",
            border_style=verdict_color,
        ))

    if not report.healthy or (strict and report.overall != OK):
        raise typer.Exit(1)


@app.command()
def agent(
    goal: Annotated[str, typer.Option("--goal", "-g", help="Natural-language goal for the agent")],
    project_path: Annotated[Optional[Path], typer.Argument(help="Project root directory")] = None,
    ue_url: Annotated[Optional[str], typer.Option("--ue-url", help="UE bridge URL")] = None,
    llm_url: Annotated[str, typer.Option("--llm-url", help="OpenAI-compatible LLM base URL")] = "http://127.0.0.1:8080/v1",
    model: Annotated[str, typer.Option("--model", help="LLM model id")] = "nvidia/nemotron-3-ultra",
    max_steps: Annotated[int, typer.Option("--max-steps", help="Max think/act iterations")] = 12,
    observe_first: Annotated[bool, typer.Option("--observe-first", help="Capture a frame before first thought")] = False,
    stream: Annotated[bool, typer.Option("--stream", help="Stream chain-of-thought to Mission Control")] = False,
    bridge_port: Annotated[int, typer.Option("--bridge-port", help="Mission Control Socket.IO port")] = 8081,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show tools/config and exit without calling the LLM")] = False,
):
    """
    Run the MVP orchestrator: LLM -> tools -> UE loop toward a goal.

    Connects to a running UE editor (HephaestusBridge HTTP server) and an
    OpenAI-compatible LLM (local llama-server or NIM), then reasons and acts
    with world.* / vision.* tools until the goal is complete.
    """
    from hephaestus_forge.runtime import UEClient, build_default_registry
    from hephaestus_forge.runtime.llm import LLMClient
    from hephaestus_forge.runtime.orchestrator import AgentRuntime, TrajectoryEvent

    resolved_ue_url = ue_url or os.environ.get("HEPHAESTUS_UE_URL", "http://127.0.0.1:8099")
    registry = build_default_registry()

    console.print(Panel.fit(
        f"[bold]Hephaestus Agent[/bold]\n"
        f"Goal: [cyan]{goal}[/cyan]\n"
        f"UE bridge: [cyan]{resolved_ue_url}[/cyan]\n"
        f"LLM: [cyan]{model} @ {llm_url}[/cyan]\n"
        f"Tools: [cyan]{', '.join(registry.names())}[/cyan]",
        border_style="green",
    ))

    if dry_run:
        console.print("[yellow]Dry run — not contacting LLM or UE.[/yellow]")
        for schema in registry.openai_schemas():
            fn = schema["function"]
            console.print(f"  • [bold]{fn['name']}[/bold]: {fn['description']}")
        return

    icons = {
        "observation": "👁️", "thought": "🧠", "action": "⚡",
        "tool_result": "✅", "error": "❌", "final": "🏁",
    }

    mission_bridge = None
    if stream:
        from hephaestus_forge.runtime.mission_bridge import MissionBridge
        mission_bridge = MissionBridge(port=bridge_port).start()
        console.print(f"[green]✓ Streaming to Mission Control on port {bridge_port}[/green]")

    def on_event(event: "TrajectoryEvent") -> None:
        icon = icons.get(event.type, "•")
        color = "red" if event.type == "error" else "cyan" if event.type == "thought" else "white"
        console.print(f"  {icon} [{color}]{event.type}[/{color}]: {event.content}")
        if mission_bridge is not None:
            mission_bridge.on_agent_event(event)

    ue_client = UEClient(base_url=resolved_ue_url)
    if not ue_client.is_healthy():
        console.print(f"[yellow]⚠ UE bridge not reachable at {resolved_ue_url}. "
                      f"Start UE via 'hephaestus_forge deploy' first.[/yellow]")

    llm = LLMClient(base_url=llm_url, model=model)
    runtime = AgentRuntime(
        llm, ue_client, registry, max_steps=max_steps, observe_first=observe_first, on_event=on_event
    )

    try:
        result = runtime.run(goal)
    finally:
        ue_client.close()
        llm.close()
        if mission_bridge is not None:
            mission_bridge.stop()

    console.print(Panel.fit(
        f"[bold]{'Completed' if result.completed else 'Stopped'}[/bold]\n"
        f"Steps: {result.steps}  Tool calls: {result.tool_calls}\n"
        f"{result.final_message}",
        border_style="green" if result.completed else "yellow",
    ))
    raise typer.Exit(0 if result.completed else 1)


if __name__ == "__main__":
    app()
