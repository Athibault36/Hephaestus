# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Offline + live checks for the production operator path (no LLM required)."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from version import BRIDGE_VERSION, FORGE_VERSION
    from plugin_sync import sync_plugin
    from preflight_health import run_preflight
except ImportError:
    from hephaestus_forge.version import BRIDGE_VERSION, FORGE_VERSION  # type: ignore
    from hephaestus_forge.plugin_sync import sync_plugin  # type: ignore
    from hephaestus_forge.preflight_health import run_preflight  # type: ignore


@dataclass
class E2EStep:
    name: str
    ok: bool
    detail: str


@dataclass
class E2EReport:
    ok: bool
    steps: list[E2EStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "forge_version": FORGE_VERSION,
            "bridge_version": BRIDGE_VERSION,
            "steps": [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in self.steps],
        }


def _post_command(remote_api: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        remote_api.rstrip("/") + "/v1/command",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def run_e2e_check(
    project_root: Path,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    sync: bool = False,
    live: bool = True,
) -> E2EReport:
    """Verify factory template, optional sync, and (when PIE is up) bridge verbs."""
    steps: list[E2EStep] = []
    root = Path(project_root).resolve()

    version_file = (
        Path(__file__).resolve().parent
        / "templates"
        / "ue_plugin"
        / "HephaestusBridge"
        / "HEPHAESTUS_BRIDGE_VERSION"
    )
    if version_file.is_file():
        steps.append(E2EStep("factory_template", True, f"Bridge template v{version_file.read_text().strip()}"))
    else:
        steps.append(E2EStep("factory_template", False, "Missing plugin template version file"))

    if sync:
        try:
            dest = sync_plugin(root)
            steps.append(E2EStep("sync_plugin", True, f"Synced -> {dest}"))
        except Exception as exc:
            steps.append(E2EStep("sync_plugin", False, str(exc)))

    installed = root / "Plugins" / "HephaestusBridge" / "HEPHAESTUS_BRIDGE_VERSION"
    if installed.is_file():
        ver = installed.read_text(encoding="utf-8").strip()
        steps.append(
            E2EStep(
                "target_plugin",
                ver == BRIDGE_VERSION,
                f"Target plugin v{ver} (factory v{BRIDGE_VERSION})",
            )
        )
    else:
        steps.append(E2EStep("target_plugin", False, "Run: forge sync-plugin <target>"))

    preflight = run_preflight(remote_api, root)
    for check in preflight.checks:
        if check.name in ("ue_pie", "bridge_capabilities", "bridge_template"):
            steps.append(E2EStep(f"preflight_{check.name}", check.ok, check.detail))

    if live and preflight.ready:
        try:
            listed = _post_command(remote_api, {"command": "world.list_actors", "params": {"include_details": True, "detail_limit": 5}})
            ok = bool(listed.get("success"))
            steps.append(E2EStep("list_actors_details", ok, listed.get("error") or "include_details ok"))
        except Exception as exc:
            steps.append(E2EStep("list_actors_details", False, str(exc)))

        try:
            cap = _post_command(remote_api, {"command": "vision.capture_frame", "params": {}})
            steps.append(E2EStep("capture_frame", bool(cap.get("success")), cap.get("error") or "ok"))
        except Exception as exc:
            steps.append(E2EStep("capture_frame", False, str(exc)))

    ok = all(s.ok for s in steps if s.name not in ("preflight_nim_api_key", "preflight_planner"))
    return E2EReport(ok=ok, steps=steps)
