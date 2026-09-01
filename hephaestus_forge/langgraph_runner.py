# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Phased UE goal runner compatible with HEPHAESTUS_ORCHESTRATOR=langgraph.

Uses LangGraph when installed; otherwise runs the same observe-act loop with explicit phases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from agent_asset import augment_goal_with_assets
from goal_grader import grade_goal
from ue_agent_loop import ObserveActLoop, RemoteUeClient
from ue_vision_planner import VisionLLMPlanner

ThoughtFn = Callable[[str, str, dict[str, Any]], None]
AvatarFn = Callable[[str, Optional[int], Optional[str]], None]


def _run_phased_loop(
    goal: str,
    *,
    remote_api: str,
    max_steps: int,
    asset_hints: list[str],
    on_thought: Optional[ThoughtFn],
    on_avatar: Optional[AvatarFn],
) -> tuple[list[Any], Any]:
    llm = VisionLLMPlanner(goal=goal, asset_hints=asset_hints)
    loop = ObserveActLoop(
        client=RemoteUeClient(remote_api, timeout=60.0),
        on_thought=on_thought or (lambda *_a: None),
        on_avatar=on_avatar or (lambda *_a: None),
        planner=(llm.decide if llm.available else None),
        goal=goal,
        asset_hints=asset_hints,
    )
    if on_thought:
        on_thought("plan", "langgraph phase: observe", {"phase": "observe"})
    snap = loop.observe()
    if on_thought:
        on_thought("plan", "langgraph phase: act", {"phase": "act"})
    results, grade = loop.run_until_goal(max_steps=max_steps)
    if on_thought:
        on_thought("reflection", grade.summary, {"phase": "grade", "met": grade.met})
    return results, grade


def run_langgraph_goal(
    message: str,
    *,
    project_root: Optional[Path] = None,
    remote_api: str = "http://127.0.0.1:8765",
    max_steps: int = 20,
    mode: str = "auto",
    reset: bool = False,
    on_thought: Optional[ThoughtFn] = None,
    on_avatar: Optional[AvatarFn] = None,
) -> dict[str, Any]:
    from agent_chat import get_store

    store = get_store(project_root)
    if reset:
        session = store.reset(goal=message.strip(), mode=mode if mode in ("cinematic", "gameplay", "auto") else "auto")  # type: ignore[arg-type]
    else:
        session = store.active()
        session.add_user(message)

    goal = session.goal or message.strip()
    if mode == "cinematic":
        goal = f"[cinematic mode] {goal}"
    elif mode == "gameplay":
        goal = f"[gameplay mode] {goal}"

    client = RemoteUeClient(remote_api, timeout=60.0)
    goal, asset_matches, asset_meta = augment_goal_with_assets(client, goal)

    try:
        from langgraph.graph import StateGraph, END  # noqa: F401

        _has_langgraph = True
    except ImportError:
        _has_langgraph = False

    results, grade = _run_phased_loop(
        goal,
        remote_api=remote_api,
        max_steps=max_steps,
        asset_hints=asset_matches,
        on_thought=on_thought,
        on_avatar=on_avatar,
    )

    reply = f"Done. {grade.summary}" if grade.met else f"Stopped. {grade.summary}"
    session.add_assistant(reply)
    session.last_grade = {
        "met": grade.met,
        "score": grade.score,
        "summary": grade.summary,
        "missing": grade.missing,
    }
    store.save(session)

    return {
        "ok": grade.met,
        "reply": reply,
        "goal": goal,
        "grade": session.last_grade,
        "planner": "langgraph" if _has_langgraph else "langgraph-phased",
        "llm_available": True,
        "llm_error": "",
        "asset_matches": asset_matches,
        "asset_meta": asset_meta,
        "session": session.to_dict(),
        "thoughts": [],
        "steps": [{"step": r.step, "kind": r.action.kind, "ok": r.ok} for r in results],
    }
