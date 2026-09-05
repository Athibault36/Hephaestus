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
    from hephaestus_forge.version import BRIDGE_VERSION, FORGE_VERSION, OPERATOR_MILESTONE
except ImportError:
    from cloud.nim_client import DEFAULT_PLANNER_MODEL, DEFAULT_VISION_MODEL  # type: ignore
    from version import BRIDGE_VERSION, FORGE_VERSION, OPERATOR_MILESTONE  # type: ignore


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
            "operator_milestone": OPERATOR_MILESTONE,
            "ue_api": self.ue_api,
            "planner_model": self.planner_model,
            "project_root": self.project_root,
            "blocker_count": len(blockers),
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "blocker": c.blocker}
                for c in self.checks
            ],
        }


def _normalize_project_dir(path: Any) -> str:
    """Compare UE ProjectDir vs forge project_root across OS path quirks."""
    p = Path(str(path)).resolve()
    # UE ProjectDir usually ends with a trailing separator conceptually; strip noise.
    text = str(p).replace("/", "\\").rstrip("\\").lower()
    return text


def fetch_ue_health(remote_api: str, timeout: float = 2.0) -> dict[str, Any]:
    url = remote_api.rstrip("/") + "/v1/health"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8") or "{}")


def pie_matches_project(health: dict[str, Any], project_root: Path) -> tuple[bool, str]:
    """Return (ok, detail) whether live PIE health belongs to project_root."""
    expected = _normalize_project_dir(project_root)
    remote_dir = str(health.get("project_dir") or "").strip()
    remote_name = str(health.get("project_name") or "").strip()
    if not remote_dir and not remote_name:
        return (
            False,
            "PIE health has no project_dir/project_name — rebuild HephaestusBridge, then Play",
        )
    if remote_dir:
        got = _normalize_project_dir(remote_dir)
        if got == expected or got.startswith(expected + "\\") or expected.startswith(got + "\\"):
            return True, f"PIE project matches ({remote_name or Path(remote_dir).name})"
        return (
            False,
            f"PIE is '{remote_name or remote_dir}' but forge target is '{project_root.name}' "
            f"— close other editors / Play the correct .uproject (got {remote_dir})",
        )
    # Name-only fallback
    if remote_name and remote_name.lower() == project_root.name.lower():
        return True, f"PIE project name matches ({remote_name})"
    return (
        False,
        f"PIE project_name '{remote_name}' != '{project_root.name}' — Play the matching .uproject",
    )


def _probe_ue(remote_api: str, timeout: float = 2.0, project_root: Optional[Path] = None) -> HealthCheck:
    url = remote_api.rstrip("/") + "/v1/health"
    try:
        body = fetch_ue_health(remote_api, timeout=timeout)
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
        else:
            detail += f" — no plugin_version in health (rebuild HephaestusBridge v{BRIDGE_VERSION})"
        detail += ")"
        if project_root is not None:
            match_ok, match_detail = pie_matches_project(body, Path(project_root))
            if not match_ok:
                return HealthCheck("ue_pie", False, match_detail, blocker=True)
            detail += f"; {match_detail}"
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
        "Set NVIDIA_API_KEY (or HEPHAESTUS_LLM_API_KEY) for Nemotron planner — heuristic fallback only",
        blocker=False,
    )


def _probe_planner() -> HealthCheck:
    try:
        try:
            from ue_vision_planner import VisionLLMPlanner
        except ImportError:
            from hephaestus_forge.ue_vision_planner import VisionLLMPlanner  # type: ignore

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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body or "{}")
        except json.JSONDecodeError:
            return {"success": False, "error": body or str(exc)}


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
        ("asset.reimport", {"command": "asset.reimport", "params": {"asset_path": "/Game/__HephaestusProbe"}}),
        ("pcg.query_spatial", {
            "command": "pcg.query_spatial",
            "params": {"min": {"x": -1, "y": -1, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}},
        }),
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
            elif label == "asset.reimport" and "not found" in err:
                pass  # probe asset missing is ok — command exists
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


def _probe_ue_editor(timeout: float = 1.5) -> HealthCheck:
    """Non-blocking: editor control API (:8766) for forge pie start/stop."""
    try:
        try:
            from pie_control import editor_online
        except ImportError:
            from hephaestus_forge.pie_control import editor_online  # type: ignore
        ok, health, detail = editor_online(timeout=timeout)
        if ok:
            pie_active = bool(health.get("pie_active"))
            hint = "PIE active" if pie_active else "PIE inactive — run forge pie start"
            return HealthCheck(
                "ue_editor",
                True,
                f"{detail}; {hint}",
                blocker=False,
            )
        return HealthCheck(
            "ue_editor",
            False,
            (
                f"{detail} — open the .uproject with HephaestusBridge rebuilt "
                f"(editor listens on :8766 for play/stop)"
            ),
            blocker=False,
        )
    except Exception as exc:
        return HealthCheck("ue_editor", False, str(exc), blocker=False)


def _probe_dcc(timeout: float = 1.5) -> HealthCheck:
    """Non-blocking: DCC control plane (:8084) for Blender/CC5."""
    try:
        try:
            from dcc_client import dcc_online
            from blender_bridge import find_blender
        except ImportError:
            from hephaestus_forge.dcc_client import dcc_online  # type: ignore
            from hephaestus_forge.blender_bridge import find_blender  # type: ignore
        ok, health, detail = dcc_online(timeout=timeout)
        path, ver = find_blender()
        blender_hint = f"Blender {ver}" if path else "Blender not installed"
        if ok:
            ready = bool(health.get("ready"))
            return HealthCheck(
                "dcc",
                True,
                f"{detail}; {blender_hint}" + ("" if ready else " (server up, Blender missing)"),
                blocker=False,
            )
        return HealthCheck(
            "dcc",
            False,
            f"{detail} — optional: forge dcc start ({blender_hint})",
            blocker=False,
        )
    except Exception as exc:
        return HealthCheck("dcc", False, str(exc), blocker=False)


def run_preflight(
    remote_api: str = "http://127.0.0.1:8765",
    project_root: Optional[Path] = None,
) -> PreflightReport:
    """Run all preflight checks. `ready` is True when UE PIE API is online."""
    checks = [
        HealthCheck("forge", True, f"HephaestusForge {FORGE_VERSION} (bridge template {BRIDGE_VERSION})", blocker=False),
        _probe_project(project_root),
        _probe_bridge_template(project_root),
        _probe_ue_editor(),
        _probe_ue(remote_api, project_root=project_root),
        _probe_bridge_capabilities(remote_api),
        _probe_dcc(),
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
