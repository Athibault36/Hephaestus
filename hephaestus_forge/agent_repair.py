# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Optional grade-failure repair pass for agent chat."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from goal_grader import GradeResult
from ue_agent_loop import ObserveActLoop

ThoughtFn = Callable[[str, str, dict[str, Any]], None]


def _maybe_nim_repair_hint(
    goal: str,
    grade: GradeResult,
    on_thought: Optional[ThoughtFn],
) -> None:
    if not on_thought:
        return
    if not os.environ.get("HEPHAESTUS_NIM_PARALLEL_REPAIR", "").strip().lower() in ("1", "true", "yes"):
        return
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("HEPHAESTUS_LLM_API_KEY") or ""
    if not key:
        return
    try:
        from cloud.parallel_nim import parallel_code

        result = parallel_code(
            f"Suggest the next single UE remote API command to fix: {', '.join(grade.missing)}",
            context=goal[:2000],
        )
        snippet = (result.merged_markdown or result.ultra_text or "")[:800]
        if snippet:
            on_thought("plan", snippet, {"source": "nim_parallel_repair"})
    except Exception as exc:
        on_thought("error", f"NIM parallel repair hint failed: {exc}", {"source": "nim_parallel_repair"})


def maybe_repair_after_grade(
    loop: ObserveActLoop,
    grade: GradeResult,
    goal: str,
    *,
    max_extra_steps: int = 6,
    on_thought: Optional[ThoughtFn] = None,
) -> tuple[list[Any], GradeResult]:
    """
    When HEPHAESTUS_NIM_REPAIR=1 and grade failed with actionable missing items,
    run a short follow-up loop with an augmented goal.
    """
    if grade.met:
        return [], grade
    if not os.environ.get("HEPHAESTUS_NIM_REPAIR", "").strip().lower() in ("1", "true", "yes"):
        return [], grade
    if not grade.missing:
        return [], grade

    _maybe_nim_repair_hint(goal, grade, on_thought)
    loop.goal = f"{goal} — still missing: {', '.join(grade.missing)}"
    extra_results, new_grade = loop.run_until_goal(max_steps=max_extra_steps)
    return extra_results, new_grade
