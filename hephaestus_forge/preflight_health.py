# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Preflight checks before Mission Control / agent goals (project-agnostic)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from hephaestus_forge.cloud.nim_client import DEFAULT_PLANNER_MODEL, DEFAULT_VISION_MODEL
    from hephaestus_forge.version import BRIDGE_VERSION, FORGE_VERSION
except ImportError:
    from cloud.nim_client import DEFAULT_PLANNER_MODEL, DEFAULT_VISION_MODEL  # type: ignore
    from version import BRIDGE_VERSION, FORGE_VERSION  # type: ignore


@dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str
    blocker: bool = True


@dataclass
class PreflightReport:
    ready: bool
    checks: list[HealthCheck] = field(default_factory=list)
    ue_api: str = ""
    planner_model: str = DEFAULT_PLANNER_MODEL
    project_root: str = ""

    def to_dict(self) -> dict[str, Any]:
        blockers = [c for c in self.checks if c.blocker and not c.ok]
        return {
            "ready": self.ready,
            "forge_version": FORGE_VERSION,
            "bridge_version": BRIDGE_VERSION,
            "ue_api": self.ue_api,
            "planner_model": self.planner_model,
            "project_root": self.project_root,
            "blocker_count": len(blockers),
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "blocker": c.blocker}
                for c in self.checks
            ],
        }


def _probe_ue(remote_api: str, timeout: float = 2.0) -> HealthCheck:
    url = remote_api.rstrip("/") + "/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return HealthCheck(
                    "ue_pie",
                    False,
                    f"UE Remote API returned HTTP {resp.status} at {url}",
                )
            import json

            body = json.loads(resp.read().decode("utf-8") or "{}")
            service = body.get("service", "hephaestus-remote")
            port = body.get("port", "")
            plugin_version = body.get("plugin_version", "")
            detail = f"Online ({service}"
            if port:
                detail += f", port {port}"
            if plugin_version:
                detail += f", plugin {plugin_version}"
                if plugin_version != BRIDGE_VERSION:
                    return HealthCheck(
                        "ue_pie",
                        True,
                        detail + f" — rebuild required (factory template v{BRIDGE_VERSION})",
                        blocker=True,
                    )
            detail += ")"
            return HealthCheck("ue_pie", True, detail, blocker=True)
    except Exception as exc:
        return HealthCheck(
            "ue_pie",
            False,
            (
                f"UE Remote API offline at {url} — open your UE 5.8 target, "
                f"enable HephaestusBridge, rebuild plugin, then Play (PIE). ({exc})"
            ),
            blocker=True,
        )


def _probe_nim_key() -> HealthCheck:
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("HEPHAESTUS_LLM_API_KEY") or ""
    if key:
        return HealthCheck("nim_api_key", True, "NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY is set")
    return HealthCheck(
        "nim_api_key",
        False,
        "Set NVIDIA_API_KEY (or HEPHAESTUS_LLM_API_KEY) for DeepSeek planner — heuristic fallback only",
        blocker=False,
    )


def _probe_planner() -> HealthCheck:
    try:
        from ue_vision_planner import VisionLLMPlanner

        llm = VisionLLMPlanner()
        if llm.available:
            return HealthCheck("planner", True, f"Planner ready ({llm.model})")
        return HealthCheck(
            "planner",
            False,
            llm.last_error or "Planner unavailable — check API key and NIM reachability",
            blocker=False,
        )
    except Exception as exc:
        return HealthCheck("planner", False, str(exc), blocker=False)


def _probe_vision_mode() -> HealthCheck:
    enabled = os.environ.get("HEPHAESTUS_PLANNER_VISION", "").strip().lower() in ("1", "true", "yes")
    vision_model = os.environ.get("HEPHAESTUS_VISION_MODEL", "").strip() or DEFAULT_VISION_MODEL
    if enabled:
        return HealthCheck(
            "vision_planner",
            True,
            f"Viewport vision enabled (caption model: {vision_model})",
            blocker=False,
        )
    return HealthCheck(
        "vision_planner",
        True,
        "Text census mode (set HEPHAESTUS_PLANNER_VISION=1 for viewport captions)",
        blocker=False,
    )


def _probe_project(project_root: Optional[Path]) -> HealthCheck:
    if not project_root:
        return HealthCheck("project", True, "No project root bound (factory mode)", blocker=False)
    root = Path(project_root)
    forge_dir = root / ".hephaestus_forge"
    if forge_dir.is_dir():
        return HealthCheck("project", True, f"Adopted target: {root.name}", blocker=False)
    return HealthCheck(
        "project",
        False,
        f"Missing .hephaestus_forge at {root} — run forge adopt <path>",
        blocker=True,
    )


def _probe_bridge_template(project_root: Optional[Path]) -> HealthCheck:
    if not project_root:
        return HealthCheck("bridge_template", True, "No project — template version only in factory", blocker=False)
    version_file = Path(project_root) / "Plugins" / "HephaestusBridge" / "HEPHAESTUS_BRIDGE_VERSION"
    if not version_file.is_file():
        return HealthCheck(
            "bridge_template",
            False,
            "Plugin not synced — run forge sync-plugin <target>",
            blocker=False,
        )
    installed = version_file.read_text(encoding="utf-8").strip()
    if installed == BRIDGE_VERSION:
        return HealthCheck("bridge_template", True, f"Plugin synced (v{installed})", blocker=False)
    return HealthCheck(
        "bridge_template",
        False,
        f"Plugin v{installed} != factory template v{BRIDGE_VERSION} — run forge sync-plugin and rebuild",
        blocker=False,
        )


def _post_command(remote_api: str, payload: dict, timeout: float = 3.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        remote_api.rstrip("/") + "/v1/command",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _probe_bridge_capabilities(remote_api: str) -> HealthCheck:
    """Verify v0.1.1+ verbs exist on the live PIE plugin (not just health version string)."""
    probes = [
        ("animation.play_locomotion", {"command": "animation.play_locomotion", "params": {}}),
        ("sequence.create_shot", {"command": "sequence.create_shot", "params": {"location": {"x": 0, "y": 0, "z": 1}}}),
        ("world.list_actors", {"command": "world.list_actors", "params": {"include_details": True, "detail_limit": 1}}),
        ("animation.play_montage", {"command": "animation.play_montage", "params": {}}),
        ("audio.play_quartz", {"command": "audio.play_quartz", "params": {"clock": "test"}}),
        ("blueprint.compile", {"command": "blueprint.compile", "params": {"blueprint_path": "/Game/__HephaestusProbe"}}),
        ("asset.create_material", {"command": "asset.create_material", "params": {"name": "HephaestusProbe"}}),
        ("asset.search", {"command": "asset.search", "params": {"query": "cube", "limit": 1}}),
        ("asset.create_instance", {
            "command": "asset.create_instance",
            "params": {"parent_material": "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"},
        }),
        ("audio.create_metasound", {"command": "audio.create_metasound", "params": {"name": "HephaestusProbe"}}),
    ]
    missing: list[str] = []
    try:
        for label, payload in probes:
            result = _post_command(remote_api, payload)
            err = str(result.get("error") or "").lower()
            if "unknown" in err or "unrecognized" in err or "not supported" in err:
                missing.append(label)
            elif label == "blueprint.compile" and "compile failed" in err:
                pass  # probe path missing is ok — command exists
            elif label == "blueprint.compile" and "subsystem" in err:
                missing.append(label)
            elif label == "audio.create_metasound" and "create_metasound" in err:
                pass  # missing source_path is ok — command exists
        if missing:
            return HealthCheck(
                "bridge_capabilities",
                False,
                f"PIE plugin missing: {', '.join(missing)} — forge sync-plugin <target> and rebuild",
                blocker=False,
            )
        return HealthCheck(
            "bridge_capabilities",
            True,
            "Locomotion, sequencer, assets, montage, audio, blueprint on PIE plugin",
            blocker=False,
        )
    except Exception as exc:
        return HealthCheck(
            "bridge_capabilities",
            False,
            f"Could not probe bridge commands ({exc})",
            blocker=False,
        )


def run_preflight(
    remote_api: str = "http://127.0.0.1:8765",
    project_root: Optional[Path] = None,
) -> PreflightReport:
    """Run all preflight checks. `ready` is True when UE PIE API is online."""
    checks = [
        HealthCheck("forge", True, f"HephaestusForge {FORGE_VERSION} (bridge template {BRIDGE_VERSION})", blocker=False),
        _probe_project(project_root),
        _probe_bridge_template(project_root),
        _probe_ue(remote_api),
        _probe_bridge_capabilities(remote_api),
        _probe_nim_key(),
        _probe_planner(),
        _probe_vision_mode(),
    ]
    ue_ok = next((c.ok for c in checks if c.name == "ue_pie"), False)
    blockers_failed = any(c.blocker and not c.ok for c in checks)
    bridge_template = next((c for c in checks if c.name == "bridge_template"), None)
    ready = ue_ok and not blockers_failed
    if project_root and bridge_template and not bridge_template.ok:
        ready = False
    ue_check = next((c for c in checks if c.name == "ue_pie"), None)
    if ue_check and ue_check.ok and "rebuild required" in ue_check.detail.lower():
        ready = False
    return PreflightReport(
        ready=ready,
        checks=checks,
        ue_api=remote_api.rstrip("/"),
        project_root=str(project_root.resolve()) if project_root else "",
    )
