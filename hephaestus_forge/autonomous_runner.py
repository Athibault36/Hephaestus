# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unified NIM-required autonomous goal runner (operator v1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from ue_agent_loop import ObserveActLoop, RemoteUeClient, StepResult
except ImportError:
    from hephaestus_forge.ue_agent_loop import ObserveActLoop, RemoteUeClient, StepResult  # type: ignore

try:
    from agent_asset import augment_goal_with_assets, spawn_asset_in_view
except ImportError:
    from hephaestus_forge.agent_asset import augment_goal_with_assets, spawn_asset_in_view  # type: ignore

try:
    from goal_grader import GradeResult
except ImportError:
    from hephaestus_forge.goal_grader import GradeResult  # type: ignore

try:
    from ue_vision_planner import VisionLLMPlanner
except ImportError:
    from hephaestus_forge.ue_vision_planner import VisionLLMPlanner  # type: ignore

ThoughtFn = Callable[[str, str, dict[str, Any]], None]
AvatarFn = Callable[[str, Optional[int], Optional[str]], None]


@dataclass
class AutonomousReport:
    ok: bool
    goal: str
    grade: dict[str, Any]
    planner: str
    llm_available: bool
    llm_error: str
    repair_passes: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    thoughts: list[dict[str, Any]] = field(default_factory=list)
    asset_matches: list[str] = field(default_factory=list)
    asset_meta: dict[str, Any] = field(default_factory=dict)
    memory: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "goal": self.goal,
            "grade": self.grade,
            "planner": self.planner,
            "llm_available": self.llm_available,
            "llm_error": self.llm_error,
            "repair_passes": self.repair_passes,
            "steps": self.steps,
            "thoughts": self.thoughts,
            "asset_matches": self.asset_matches,
            "asset_meta": self.asset_meta,
            "memory": self.memory,
        }


def _steps_payload(results: list[StepResult]) -> list[dict[str, Any]]:
    return [
        {
            "step": r.step,
            "kind": r.action.kind,
            "reason": r.action.reason,
            "ok": r.ok,
            "lights": r.reobservation.lights,
            "meshes": r.reobservation.meshes,
            "skeletal": r.reobservation.skeletal,
        }
        for r in results
    ]


def _grade_dict(grade: GradeResult) -> dict[str, Any]:
    return {
        "met": grade.met,
        "score": grade.score,
        "summary": grade.summary,
        "missing": grade.missing,
    }


def run_autonomous_goal(
    goal: str,
    *,
    project_root: Optional[Path] = None,
    remote_api: str = "http://127.0.0.1:8765",
    max_steps: int = 24,
    repair: bool = True,
    max_repair_steps: int = 6,
    mode: str = "auto",
    require_nim: bool = True,
    prefetch_spawn: bool = True,
    session_memory: Optional[list[dict[str, Any]]] = None,
    on_thought: Optional[ThoughtFn] = None,
    on_avatar: Optional[AvatarFn] = None,
) -> AutonomousReport:
    """
    Run observe→act with NIM planner until grade passes or budget exhausted.

    When ``require_nim`` is True and no API key is configured, returns immediately
    with ``llm_error`` (no heuristic fallback).
    """
    _ = project_root  # reserved for session persistence by callers
    raw_goal = (goal or "").strip()
    if mode == "cinematic":
        raw_goal = f"[cinematic mode] {raw_goal}"
    elif mode == "gameplay":
        raw_goal = f"[gameplay mode] {raw_goal}"

    client = RemoteUeClient(remote_api, timeout=60.0)
    try:
        client.health()
    except Exception as exc:
        return AutonomousReport(
            ok=False,
            goal=raw_goal,
            grade={"met": False, "score": 0.0, "summary": f"PIE unreachable: {exc}", "missing": ["ue_pie"]},
            planner="",
            llm_available=False,
            llm_error=str(exc),
        )

    augmented_goal, asset_matches, asset_meta = augment_goal_with_assets(client, raw_goal)
    llm = VisionLLMPlanner(goal=augmented_goal, asset_hints=asset_matches)
    if require_nim and not llm.available:
        err = llm.last_error or "NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY required for autonomous v1"
        return AutonomousReport(
            ok=False,
            goal=augmented_goal,
            grade={"met": False, "score": 0.0, "summary": err, "missing": ["nim_planner"]},
            planner="",
            llm_available=False,
            llm_error=err,
            asset_matches=asset_matches,
            asset_meta=asset_meta,
        )

    if prefetch_spawn and len(asset_matches) == 1 and "direct_spawn" not in asset_meta:
        try:
            spawn_asset_in_view(client, asset_matches[0])
            asset_meta["prefetch_spawn"] = asset_matches[0]
        except Exception:
            pass

    thoughts: list[dict[str, Any]] = []

    def _thought(kind: str, content: str, metadata: dict[str, Any]) -> None:
        thoughts.append({"kind": kind, "content": content, "metadata": metadata})
        if on_thought:
            on_thought(kind, content, metadata)

    loop = ObserveActLoop(
        client=client,
        on_thought=_thought,
        on_avatar=on_avatar or (lambda *_a, **_k: None),
        planner=llm.decide if llm.available else None,
        goal=augmented_goal,
        asset_hints=asset_matches,
        require_nim=require_nim,
    )
    if session_memory:
        loop.memory = list(session_memory)

    _thought("plan", f"Autonomous: {augmented_goal[:240]}", {"mode": mode})
    step_budget = max(max_steps, 16) if asset_matches else max_steps
    results, grade = loop.run_until_goal(max_steps=step_budget)
    repair_passes = 0

    last_kind = results[-1].action.kind if results else ""
    last_err = (results[-1].act_result or {}).get("error") if results else ""
    fatal = last_kind == "llm_error" or "PIE offline" in str(last_err or "")

    if repair and not grade.met and not fatal:
        try:
            from agent_repair import maybe_repair_after_grade

            extra_results, grade = maybe_repair_after_grade(
                loop,
                grade,
                augmented_goal,
                max_extra_steps=max_repair_steps,
                on_thought=_thought,
                force=True,
            )
            if extra_results:
                repair_passes = 1
                results.extend(extra_results)
        except ImportError:
            pass

    grade_dict = _grade_dict(grade)
    llm_error = llm.last_error or ""
    if require_nim and not llm.available:
        llm_error = llm_error or "NVIDIA_API_KEY not set"
    if fatal and results:
        llm_error = llm_error or results[-1].action.reason or str(last_err or "")
        if "PIE offline" in str(last_err or "") or "PIE offline" in (results[-1].action.reason or ""):
            grade_dict = {
                "met": False,
                "score": 0.0,
                "summary": results[-1].action.reason or str(last_err),
                "missing": ["ue_pie"],
            }
        elif last_kind == "llm_error":
            grade_dict = {
                "met": False,
                "score": grade_dict.get("score", 0.0),
                "summary": results[-1].action.reason or grade_dict.get("summary", "planner failed"),
                "missing": list(dict.fromkeys([*(grade_dict.get("missing") or []), "nim_planner"])),
            }

    return AutonomousReport(
        ok=grade.met and not fatal,
        goal=augmented_goal,
        grade=grade_dict,
        planner=llm.model if llm.available else "heuristic",
        llm_available=llm.available,
        llm_error=llm_error,
        repair_passes=repair_passes,
        steps=_steps_payload(results),
        thoughts=thoughts[-40:],
        asset_matches=asset_matches,
        asset_meta=asset_meta,
        memory=loop.memory,
    )
