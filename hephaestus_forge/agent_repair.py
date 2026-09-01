# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Optional grade-failure repair pass for agent chat."""

from __future__ import annotations

import os
from typing import Any, Optional

from goal_grader import GradeResult
from ue_agent_loop import ObserveActLoop


def maybe_repair_after_grade(
    loop: ObserveActLoop,
    grade: GradeResult,
    goal: str,
    *,
    max_extra_steps: int = 6,
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

    loop.goal = f"{goal} — still missing: {', '.join(grade.missing)}"
    extra_results, new_grade = loop.run_until_goal(max_steps=max_extra_steps)
    return extra_results, new_grade
