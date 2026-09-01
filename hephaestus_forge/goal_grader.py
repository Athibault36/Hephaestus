# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Heuristic goal grading for observe-act loop (v0)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class GradeResult:
    met: bool
    score: float
    summary: str
    missing: list[str]


def _extract_min_count(goal: str, patterns: list[str], default: int = 0) -> int:
    goal_l = goal.lower()
    for pat in patterns:
        m = re.search(pat, goal_l)
        if m:
            return max(int(m.group(1)), 0)
    return default


def _has_gradable_criteria(goal_l: str, min_lights: int, min_meshes: int, min_skeletal: int) -> bool:
    """True when the goal text implies census thresholds we can check."""
    if min_lights or min_meshes or min_skeletal:
        return True
    if re.search(r"\d", goal_l):
        return True
    hints = (
        "lit", "light", "cube", "mesh", "object", "seed", "scene",
        "camera", "spotlight", "color", "red", "blue", "green", "warm", "cool",
        "idle", "hold", "done", "walk", "anim", "playing", "character", "skeletal",
        "jog", "run", "move", "forward", "pawn",
        "frame", "shot", "cinematic", "dog", "cat", "creature",
        "material", "shader", "audio", "sound", "music",
    )
    return any(h in goal_l for h in hints)


def _actor_path_from_goal(goal: str) -> Optional[str]:
    paths = re.findall(r"/Temp/[^\s,;\"']+", goal or "")
    return paths[-1] if paths else None


def _anim_playing_for_actor(details: list[Any], actor_path: str) -> bool:
    for detail in details:
        if not isinstance(detail, dict):
            continue
        path = str(detail.get("actor_path") or "")
        if path == actor_path or actor_path in path or path in actor_path:
            return bool(detail.get("anim_playing"))
    return False


def _montage_command_succeeded(memory: Optional[list[dict[str, Any]]], actor_path: str = "") -> bool:
    for step in memory or []:
        if not step.get("ok"):
            continue
        if step.get("kind") != "play_montage" and step.get("command") != "animation.play_montage":
            continue
        if actor_path:
            step_actor = str(step.get("actor_path") or "")
            if step_actor and actor_path not in step_actor and step_actor not in actor_path:
                continue
        return True
    return False


def _locomotion_command_succeeded(memory: Optional[list[dict[str, Any]]], actor_path: str = "") -> bool:
    for step in memory or []:
        if not step.get("ok"):
            continue
        if step.get("kind") not in ("play_locomotion",) and step.get("command") != "animation.play_locomotion":
            continue
        if actor_path:
            step_actor = str(step.get("actor_path") or "")
            if step_actor and actor_path not in step_actor and step_actor not in actor_path:
                continue
        return True
    return False


def _animation_command_succeeded(
    memory: Optional[list[dict[str, Any]]],
    actor_path: str = "",
) -> bool:
    anim_kinds = frozenset({"play_anim", "play_montage", "play_locomotion"})
    anim_cmds = frozenset({
        "animation.play_sequence",
        "animation.play_montage",
        "animation.play_locomotion",
    })
    for step in memory or []:
        if not step.get("ok"):
            continue
        if step.get("kind") not in anim_kinds and step.get("command") not in anim_cmds:
            continue
        if actor_path:
            step_actor = str(step.get("actor_path") or "")
            if step_actor and actor_path not in step_actor and step_actor not in actor_path:
                continue
        return True
    return False


def _extract_game_paths(text: str) -> list[str]:
    return re.findall(r"/Game/[^\s,;\"']+", text or "")


def _mesh_paths_in_snapshot(snapshot: Any) -> set[str]:
    paths: set[str] = set()
    for detail in getattr(snapshot, "actor_details", None) or []:
        if not isinstance(detail, dict):
            continue
        mesh = detail.get("mesh_path") or ""
        if mesh:
            paths.add(str(mesh))
    return paths


def _spawned_mesh_paths(memory: Optional[list[dict[str, Any]]]) -> set[str]:
    out: set[str] = set()
    for step in memory or []:
        mesh = step.get("mesh_path")
        if mesh:
            out.add(str(mesh))
    return out


def _asset_goal_satisfied(goal: str, snapshot: Any, memory: Optional[list[dict[str, Any]]]) -> bool:
    """True when a /Game asset path named in the goal appears in scene or spawn memory."""
    wanted = _extract_game_paths(goal)
    if not wanted:
        return False
    scene = _mesh_paths_in_snapshot(snapshot)
    spawned = _spawned_mesh_paths(memory)
    for path in wanted:
        base = path.rsplit(".", 1)[0]
        for seen in scene | spawned:
            if path in seen or seen in path or base in seen:
                return True
    return False


def _meaningful_steps(memory: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if not memory:
        return []
    skip_kinds = {"noop"}
    skip_cmds = {"world.list_actors", "vision.capture_frame"}
    out: list[dict[str, Any]] = []
    for step in memory:
        if step.get("kind") in skip_kinds:
            continue
        if step.get("command") in skip_cmds:
            continue
        if step.get("ok"):
            out.append(step)
    return out


def _scene_matches_goal_tokens(goal_l: str, snapshot: Any) -> bool:
    stop = frozenset({
        "the", "and", "with", "for", "from", "into", "front", "camera", "scene",
        "make", "seed", "lit", "light", "cube", "mesh", "spawn", "play", "idle",
    })
    tokens = [t for t in re.findall(r"[a-z]{3,}", goal_l) if t not in stop]
    if not tokens:
        return False
    for detail in getattr(snapshot, "actor_details", None) or []:
        if not isinstance(detail, dict):
            continue
        blob = " ".join(
            str(detail.get(k, ""))
            for k in ("mesh_path", "class", "actor_path")
        ).lower()
        if any(t in blob for t in tokens):
            return True
    return False


def _creature_keywords(goal_l: str) -> list[str]:
    words = ("dog", "cat", "wolf", "horse", "bird", "creature", "dragon", "fox")
    return [w for w in words if w in goal_l]


def _camera_goal(goal_l: str) -> bool:
    if any(w in goal_l for w in ("frame", "shot", "cinematic")):
        return True
    return "camera" in goal_l and any(w in goal_l for w in ("left", "right", "from", "move", "pan"))


def _camera_repositioned(memory: Optional[list[dict[str, Any]]]) -> bool:
    for step in memory or []:
        if step.get("kind") in ("set_view", "create_shot", "play_level_sequence") and step.get("ok"):
            return True
        cmd = step.get("command") or ""
        if cmd in ("world.set_view", "sequence.create_shot", "sequence.play") and step.get("ok"):
            return True
    return False


def _audio_command_succeeded(memory: Optional[list[dict[str, Any]]]) -> bool:
    audio_cmds = frozenset({
        "audio.play_quartz",
        "audio.create_metasound",
        "audio.synthesize",
    })
    for step in memory or []:
        if not step.get("ok"):
            continue
        if step.get("command") in audio_cmds:
            return True
        if step.get("kind") in ("play_audio", "create_metasound"):
            return True
    return False


def _audio_goal(goal_l: str) -> bool:
    return any(w in goal_l for w in ("sound", "audio", "music", "metasound", "quartz"))


def _material_command_succeeded(memory: Optional[list[dict[str, Any]]]) -> bool:
    material_cmds = frozenset({
        "asset.create_material",
        "asset.create_instance",
    })
    for step in memory or []:
        if step.get("ok") and step.get("command") in material_cmds:
            return True
        if step.get("ok") and step.get("kind") in ("create_material", "create_instance"):
            return True
    return False


def _material_goal(goal_l: str) -> bool:
    return any(w in goal_l for w in ("material", "metallic", "shader", "mid", "instance"))


def grade_goal(goal: str, snapshot: Any, memory: Optional[list[dict[str, Any]]] = None) -> GradeResult:
    """
    v0: census-based grading for seed-scene goals.
    Returns met=True when lights/meshes thresholds implied by goal are satisfied.
    """
    goal_l = (goal or "").strip().lower()
    if not goal_l:
        return GradeResult(met=True, score=1.0, summary="No goal set", missing=[])

    min_lights = _extract_min_count(goal, [r"(\d+)\s*lights?", r"at least (\d+) light"], 0)
    min_meshes = _extract_min_count(goal, [r"(\d+)\s*cubes?", r"(\d+)\s*meshes?", r"at least (\d+) cube"], 0)
    min_skeletal = _extract_min_count(goal, [r"(\d+)\s*characters?", r"(\d+)\s*skeletal"], 0)
    lights = int(getattr(snapshot, "lights", 0) or 0)
    meshes = int(getattr(snapshot, "meshes", 0) or 0)
    skeletal = int(getattr(snapshot, "skeletal", 0) or 0)

    # Common seed phrases
    if "lit" in goal_l or "light" in goal_l:
        min_lights = max(min_lights, 1)
    if "cube" in goal_l or re.search(r"\bmesh(es)?\b", goal_l) or "object" in goal_l:
        min_meshes = max(min_meshes, 1)
    if "few cubes" in goal_l or "some cubes" in goal_l:
        min_meshes = max(min_meshes, 3)
    if "seed" in goal_l and min_meshes == 0:
        min_meshes = max(min_meshes, 2)

    if "character" in goal_l or "skeletal" in goal_l or "walk" in goal_l or "anim" in goal_l:
        min_skeletal = max(min_skeletal, 1)

    creatures = _creature_keywords(goal_l)
    if creatures:
        min_skeletal = max(min_skeletal, 1)

    anim_playing = False
    details = getattr(snapshot, "actor_details", None) or []
    if isinstance(details, list):
        target_actor = _actor_path_from_goal(goal)
        if target_actor and ("idle" in goal_l or "anim" in goal_l):
            anim_playing = _anim_playing_for_actor(details, target_actor)
            if not anim_playing and _animation_command_succeeded(memory, target_actor):
                anim_playing = True
        else:
            anim_playing = any(bool(d.get("anim_playing")) for d in details if isinstance(d, dict))
            if not anim_playing and _animation_command_succeeded(memory):
                anim_playing = True

    missing: list[str] = []
    if lights < min_lights:
        missing.append(f"lights {lights}/{min_lights}")
    if meshes < min_meshes:
        missing.append(f"meshes {meshes}/{min_meshes}")
    if skeletal < min_skeletal:
        missing.append(f"skeletal {skeletal}/{min_skeletal}")
    if ("playing" in goal_l or "walk" in goal_l or "anim" in goal_l or "idle" in goal_l or "run" in goal_l) and min_skeletal > 0 and not anim_playing:
        wants_montage = "montage" in goal_l
        target_actor = _actor_path_from_goal(goal) or ""
        if wants_montage and not _montage_command_succeeded(memory, target_actor):
            missing.append("montage not playing")
        elif "idle" in goal_l and not _locomotion_command_succeeded(memory, target_actor) and not anim_playing:
            missing.append("idle animation not playing")
        elif "run" in goal_l and not _locomotion_command_succeeded(memory, target_actor) and not anim_playing:
            missing.append("run animation not playing")
        elif "walk" in goal_l and not _locomotion_command_succeeded(memory, target_actor) and not anim_playing:
            missing.append("walk animation not playing")
        elif not wants_montage:
            missing.append("animation not playing")

    if ("level sequence" in goal_l or ("sequence" in goal_l and "/game/" in goal_l)):
        played = any(
            (step.get("command") == "sequence.play" or step.get("kind") == "play_level_sequence")
            and step.get("ok")
            for step in (memory or [])
        )
        if not played:
            missing.append("level sequence not playing")
    elif "sequence.play" in goal_l or "play level sequence" in goal_l:
        played = any(
            step.get("command") == "sequence.play" and step.get("ok")
            for step in (memory or [])
        )
        if not played:
            missing.append("level sequence not playing")

    pawn_state = getattr(snapshot, "pawn_state", None) or {}
    pawn_speed = float(pawn_state.get("speed") or 0.0) if isinstance(pawn_state, dict) else 0.0
    wants_movement = any(w in goal_l for w in ("jog", "run forward", "walk forward", "move pawn", "move forward"))
    if wants_movement and pawn_speed < 10.0:
        missing.append(f"pawn not moving (speed={pawn_speed:.0f})")

    if _camera_goal(goal_l) and not _camera_repositioned(memory):
        missing.append("camera not repositioned")

    if _audio_goal(goal_l) and not _audio_command_succeeded(memory):
        missing.append("audio not played")

    if _material_goal(goal_l) and not _material_command_succeeded(memory):
        missing.append("material not created")

    if creatures and skeletal >= min_skeletal and not _scene_matches_goal_tokens(goal_l, snapshot):
        if not _asset_goal_satisfied(goal, snapshot, memory):
            missing.append(f"creature goal ({', '.join(creatures)}) not matched in scene assets")

    if "idle" in goal_l or "hold" in goal_l or "done" in goal_l:
        if not missing:
            return GradeResult(met=True, score=1.0, summary="Seed goal satisfied", missing=[])

    gradable = _has_gradable_criteria(goal_l, min_lights, min_meshes, min_skeletal)
    if _extract_game_paths(goal) and not _asset_goal_satisfied(goal, snapshot, memory):
        missing.append("named asset not spawned yet")

    if not missing and not gradable:
        if _meaningful_steps(memory) and (
            _scene_matches_goal_tokens(goal_l, snapshot) or _asset_goal_satisfied(goal, snapshot, memory)
        ):
            return GradeResult(met=True, score=1.0, summary="Scene matches goal subject", missing=[])
        if not _meaningful_steps(memory):
            return GradeResult(
                met=False,
                score=0.0,
                summary=(
                    "Cannot verify this goal from scene census alone — "
                    "use a concrete scene ask (e.g. lit cubes in front of camera) "
                    "or provide an asset path (e.g. /Game/Meshes/Dog.Dog)."
                ),
                missing=["needs concrete criteria or asset path"],
            )

    if not missing:
        if _asset_goal_satisfied(goal, snapshot, memory):
            return GradeResult(met=True, score=1.0, summary="Requested asset is in the scene", missing=[])
        return GradeResult(met=True, score=1.0, summary="Goal thresholds met", missing=[])

    total = max(min_lights, 1) + max(min_meshes, 1) + max(min_skeletal, 1)
    have = min(lights, min_lights) + min(meshes, min_meshes) + min(skeletal, min_skeletal)
    score = have / total if total else 0.0
    return GradeResult(
        met=False,
        score=score,
        summary="Still working: " + ", ".join(missing),
        missing=missing,
    )
