# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unified production operator gate (offline + optional live PIE)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from doctor import run_doctor
    from mission_control_build import is_vite_build, mc_dist_path
    from version import BRIDGE_VERSION, FORGE_VERSION, OPERATOR_MILESTONE
except ImportError:
    from hephaestus_forge.doctor import run_doctor  # type: ignore
    from hephaestus_forge.mission_control_build import is_vite_build, mc_dist_path  # type: ignore
    from hephaestus_forge.version import BRIDGE_VERSION, FORGE_VERSION, OPERATOR_MILESTONE  # type: ignore


@dataclass
class GateStep:
    name: str
    ok: bool
    detail: str
    blocker: bool = True


@dataclass
class OperatorGateReport:
    ok: bool
    milestone: str = OPERATOR_MILESTONE
    steps: list[GateStep] = field(default_factory=list)
    doctor: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        blockers = [s for s in self.steps if s.blocker and not s.ok]
        return {
            "ok": self.ok,
            "milestone": self.milestone,
            "forge_version": FORGE_VERSION,
            "bridge_version": BRIDGE_VERSION,
            "blocker_count": len(blockers),
            "steps": [
                {"name": s.name, "ok": s.ok, "detail": s.detail, "blocker": s.blocker}
                for s in self.steps
            ],
            "doctor": self.doctor,
        }


def _mc_build_ok(project_root: Optional[Path]) -> GateStep:
    if not project_root:
        return GateStep("mission_control_dist", True, "No project — skip MC dist check", blocker=False)
    dist = mc_dist_path(Path(project_root))
    if dist.is_dir() and is_vite_build(dist):
        return GateStep("mission_control_dist", True, f"Vite build at {dist}", blocker=False)
    return GateStep(
        "mission_control_dist",
        False,
        f"Missing Mission Control dist — run: forge build-mc {project_root}",
        blocker=False,
    )


def run_operator_gate(
    project_root: Optional[Path] = None,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    sync: bool = False,
    live: bool = True,
) -> OperatorGateReport:
    """Run doctor + packaging checks. `ok` when blockers pass."""
    root = Path(project_root).resolve() if project_root else None
    doctor_report = run_doctor(root, remote_api=remote_api, sync=sync, live=live and root is not None)
    steps: list[GateStep] = [
        GateStep("forge_version", True, f"HephaestusForge {FORGE_VERSION} (bridge {BRIDGE_VERSION})"),
        _mc_build_ok(root),
    ]
    for step in doctor_report.e2e.get("steps", []):
        name = str(step.get("name") or "")
        if name in ("factory_template", "target_plugin"):
            steps.append(
                GateStep(
                    f"e2e_{name}",
                    bool(step.get("ok")),
                    str(step.get("detail") or ""),
                )
            )
    if live and root is not None:
        ue = next((c for c in doctor_report.preflight.get("checks", []) if c.get("name") == "ue_pie"), None)
        steps.append(
            GateStep(
                "preflight_ue_pie",
                bool(ue and ue.get("ok")),
                str(ue.get("detail") if ue else "ue_pie missing"),
            )
        )
        cap = next(
            (c for c in doctor_report.preflight.get("checks", []) if c.get("name") == "bridge_capabilities"),
            None,
        )
        steps.append(
            GateStep(
                "preflight_bridge_capabilities",
                bool(cap and cap.get("ok")),
                str(cap.get("detail") if cap else "bridge_capabilities missing"),
                blocker=False,
            )
        )
    blockers_failed = any(s.blocker and not s.ok for s in steps)
    # Offline gate ignores doctor.ok when live PIE was not requested.
    gate_ok = (not blockers_failed) if not live else (doctor_report.ok and not blockers_failed)
    return OperatorGateReport(
        ok=gate_ok,
        steps=steps,
        doctor=doctor_report.to_dict(),
    )
