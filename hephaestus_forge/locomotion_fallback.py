# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Engine / mannequin animation fallbacks when project asset search misses."""

from __future__ import annotations

import re
from typing import Optional

from pathlib import Path

# Tried in order by animation.play_locomotion in the UE plugin.
FALLBACK_IDLE: tuple[str, ...] = (
    "/Game/Characters/Mannequins/Animations/Manny/MM_Idle.MM_Idle",
    "/Game/Characters/Mannequins/Animations/Quinn/MF_Idle.MF_Idle",
    "/Game/ThirdPerson/Animations/ThirdPersonIdle.ThirdPersonIdle",
)

FALLBACK_WALK: tuple[str, ...] = (
    "/Game/Characters/Mannequins/Animations/Manny/MM_Walk_InPlace.MM_Walk_InPlace",
    "/Game/Characters/Mannequins/Animations/Quinn/MF_Walk_InPlace.MF_Walk_InPlace",
    "/Game/ThirdPerson/Animations/ThirdPersonWalk.ThirdPersonWalk",
)

FALLBACK_RUN: tuple[str, ...] = (
    "/Game/Characters/Mannequins/Animations/Manny/MM_Run_InPlace.MM_Run_InPlace",
    "/Game/Characters/Mannequins/Animations/Quinn/MF_Run_InPlace.MF_Run_InPlace",
    "/Game/ThirdPerson/Animations/ThirdPersonRun.ThirdPersonRun",
)


def infer_locomotion_mode(goal: str) -> Optional[str]:
    """Return idle, walk, or run when the goal implies locomotion playback."""
    goal_l = (goal or "").lower()
    if "idle" in goal_l or "hold still" in goal_l:
        return "idle"
    if re.search(r"\brun\b", goal_l):
        return "run"
    if "walk" in goal_l or "jog" in goal_l:
        return "walk"
    return None


def fallback_paths_for_mode(mode: str, project_root: Optional[Path] = None) -> tuple[str, ...]:
    mode_l = (mode or "").lower()
    if project_root:
        cfg_path = Path(project_root) / ".hephaestus_forge" / "locomotion.json"
        if cfg_path.is_file():
            try:
                import json

                raw = json.loads(cfg_path.read_text(encoding="utf-8"))
                paths = raw.get(mode_l)
                if isinstance(paths, list) and paths:
                    return tuple(str(p) for p in paths)
            except (json.JSONDecodeError, OSError):
                pass
    if mode_l == "run":
        return FALLBACK_RUN
    if mode_l == "walk":
        return FALLBACK_WALK
    return FALLBACK_IDLE


def pick_fallback_anim_path(goal: str) -> Optional[str]:
    mode = infer_locomotion_mode(goal)
    if not mode:
        return None
    paths = fallback_paths_for_mode(mode)
    return paths[0] if paths else None
