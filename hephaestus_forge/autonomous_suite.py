# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Operator A–G autonomous acceptance suite (v1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from autonomous_runner import AutonomousReport, run_autonomous_goal
    from mission_control_build import is_vite_build, mc_dist_path
    from operator_gate import run_operator_gate
    from version import OPERATOR_MILESTONE
except ImportError:
    from hephaestus_forge.autonomous_runner import AutonomousReport, run_autonomous_goal  # type: ignore
    from hephaestus_forge.mission_control_build import is_vite_build, mc_dist_path  # type: ignore
    from hephaestus_forge.operator_gate import run_operator_gate  # type: ignore
    from hephaestus_forge.version import OPERATOR_MILESTONE  # type: ignore

ThoughtFn = Callable[[str, str, dict[str, Any]], None]


@dataclass
class SuiteScenario:
    id: str
    name: str
    kind: str  # autonomous | direct | infra
    goal: str = ""
    require_nim: bool = True


@dataclass
class SuiteStepResult:
    scenario_id: str
    ok: bool
    detail: str
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteReport:
    ok: bool
    milestone: str = OPERATOR_MILESTONE
    steps: list[SuiteStepResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "milestone": self.milestone,
            "step_count": len(self.steps),
            "failed": [s.scenario_id for s in self.steps if not s.ok],
            "steps": [
                {
                    "scenario_id": s.scenario_id,
                    "ok": s.ok,
                    "detail": s.detail,
                    "report": s.report,
                }
                for s in self.steps
            ],
        }


SUITE_SCENARIOS: list[SuiteScenario] = [
    SuiteScenario("C", "Mission Control dist", "infra"),
    SuiteScenario("D", "Operator gate (offline blockers)", "infra"),
    SuiteScenario(
        "A",
        "Spawn creature and walk",
        "autonomous",
        "Spawn a dog in front of the camera and make it walk",
    ),
    SuiteScenario(
        "B",
        "Cinematic framing",
        "autonomous",
        "Frame the character in a cinematic shot from the left",
    ),
    SuiteScenario("E1", "Direct spawn path", "direct", "/Game/Meshes/Dog.Dog"),
    SuiteScenario("E2", "Direct locomotion", "direct", "play walk animation on /Temp/PlaceholderActor"),
    SuiteScenario("E3", "Direct audio", "direct", "play test audio"),
    SuiteScenario("E4", "Direct asset search", "direct", "search assets for dog"),
    SuiteScenario(
        "F",
        "Asset pipeline validation",
        "autonomous",
        "Create a metallic material in the project, then try to reimport /Game/MissingAsset with a clear error",
    ),
    SuiteScenario(
        "G1",
        "Grade material",
        "autonomous",
        "Create a metallic material for the scene",
    ),
    SuiteScenario("G2", "Grade audio", "autonomous", "Play test audio in the level"),
    SuiteScenario(
        "G3",
        "Grade camera",
        "autonomous",
        "Frame the character from the left with the camera",
    ),
    SuiteScenario(
        "G4",
        "Grade displacement",
        "autonomous",
        "Make the character walk forward and verify displacement",
    ),
]


def _infra_c(project_root: Path) -> SuiteStepResult:
    dist = mc_dist_path(project_root)
    ok = dist.is_dir() and is_vite_build(dist)
    return SuiteStepResult(
        "C",
        ok,
        f"Mission Control dist at {dist}" if ok else f"Missing MC dist — run: forge build-mc {project_root}",
    )


def _infra_d(project_root: Path, *, live: bool) -> SuiteStepResult:
    gate = run_operator_gate(project_root, live=live)
    blockers = [s for s in gate.steps if s.blocker and not s.ok]
    return SuiteStepResult(
        "D",
        gate.ok,
        "gate ok" if gate.ok else f"{len(blockers)} blocker(s)",
        report=gate.to_dict(),
    )


def run_autonomous_suite(
    project_root: Path,
    *,
    remote_api: str = "http://127.0.0.1:8765",
    scenario_filter: Optional[list[str]] = None,
    live: bool = True,
    skip_nim: bool = False,
    on_thought: Optional[ThoughtFn] = None,
) -> SuiteReport:
    """Run operator A–G suite. Infra steps C/D always run first when included."""
    root = Path(project_root).resolve()
    selected = {
        s.id.upper(): s
        for s in SUITE_SCENARIOS
        if not scenario_filter or s.id.upper() in {x.upper() for x in scenario_filter}
    }
    steps: list[SuiteStepResult] = []

    order = ["C", "D", "A", "B", "E1", "E2", "E3", "E4", "F", "G1", "G2", "G3", "G4"]
    for sid in order:
        scenario = selected.get(sid)
        if not scenario:
            continue
        if scenario.kind == "infra":
            if sid == "C":
                steps.append(_infra_c(root))
            elif sid == "D":
                steps.append(_infra_d(root, live=live))
            continue

        if scenario.kind == "direct":
            try:
                from agent_chat import run_chat
            except ImportError:
                from hephaestus_forge.agent_chat import run_chat  # type: ignore
            out = run_chat(
                scenario.goal,
                project_root=root,
                remote_api=remote_api,
                reset=True,
                on_thought=on_thought,
            )
            steps.append(
                SuiteStepResult(
                    sid,
                    bool(out.get("ok")),
                    str(out.get("reply") or out.get("grade", {}).get("summary", "")),
                    report={"planner": out.get("planner"), "grade": out.get("grade")},
                )
            )
            continue

        if skip_nim:
            steps.append(SuiteStepResult(sid, True, "skipped (offline — NIM goals not run)", report={}))
            continue

        report: AutonomousReport = run_autonomous_goal(
            scenario.goal,
            project_root=root,
            remote_api=remote_api,
            require_nim=True,
            repair=True,
            on_thought=on_thought,
        )
        steps.append(
            SuiteStepResult(
                sid,
                report.ok,
                report.grade.get("summary", ""),
                report=report.to_dict(),
            )
        )

    ok = all(s.ok for s in steps) if steps else False
    return SuiteReport(ok=ok, steps=steps)
