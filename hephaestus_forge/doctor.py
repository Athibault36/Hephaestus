# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unified operator doctor: offline e2e + preflight + rebuild checklist."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from e2e_check import run_e2e_check
    from preflight_health import run_preflight
    from version import BRIDGE_VERSION, FORGE_VERSION
except ImportError:
    from hephaestus_forge.e2e_check import run_e2e_check  # type: ignore
    from hephaestus_forge.preflight_health import run_preflight  # type: ignore
    from hephaestus_forge.version import BRIDGE_VERSION, FORGE_VERSION  # type: ignore


@dataclass
class DoctorReport:
    ok: bool
    checklist: list[str] = field(default_factory=list)
    e2e: dict[str, Any] = field(default_factory=dict)
    preflight: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "forge_version": FORGE_VERSION,
            "bridge_version": BRIDGE_VERSION,
            "checklist": self.checklist,
            "e2e": self.e2e,
            "preflight": self.preflight,
        }


def rebuild_checklist(project_root: Optional[Path] = None) -> list[str]:
    target = f"<PATH-TO-UE-PROJECT>" if not project_root else str(project_root)
    return [
        f"git pull && forge sync-plugin {target}",
        "UE 5.8: enable HephaestusBridge, rebuild Development Editor, disable Live Coding",
        "Play (PIE) in the target project",
        f"forge health {target}  # expect plugin_version {BRIDGE_VERSION}",
        f"forge e2e {target}  # live probes when PIE is up",
        f"forge observe {target}  # Mission Control on :3000",
        f"forge build-mc {target}  # optional React UI (Node.js)",
    ]


def run_doctor(
    project_root: Optional[Path] = None,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    sync: bool = False,
    live: bool = True,
) -> DoctorReport:
    root = Path(project_root).resolve() if project_root else None
    checklist = rebuild_checklist(root)
    e2e_report = run_e2e_check(root or Path.cwd(), remote_api=remote_api, sync=sync, live=live and root is not None)
    preflight = run_preflight(remote_api, root)
    ok = e2e_report.ok and preflight.ready
    return DoctorReport(
        ok=ok,
        checklist=checklist,
        e2e=e2e_report.to_dict(),
        preflight=preflight.to_dict(),
    )
