# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Project asset search helpers for chat-driven goals."""

from __future__ import annotations

import json
import re
from typing import Any

try:
    from ue_agent_loop import RemoteUeClient
except ImportError:
    from hephaestus_forge.ue_agent_loop import RemoteUeClient  # type: ignore

_STOP = frozenset({
    "the", "and", "with", "for", "from", "into", "front", "camera", "scene",
    "make", "seed", "lit", "light", "cube", "mesh", "spawn", "play", "idle",
})


def search_project_assets(
    client: RemoteUeClient,
    query: str,
    *,
    asset_class: str = "",
    limit: int = 12,
) -> list[str]:
    """Return object paths from asset.search (empty if command unavailable)."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        res = client.command({
            "command": "asset.search",
            "params": {"query": query, "class": asset_class, "limit": limit},
        })
    except Exception:
        return []
    if not res.get("success"):
        return []
    try:
        inner = json.loads(res.get("result_json") or "{}")
    except json.JSONDecodeError:
        return []
    assets = inner.get("assets") or []
    return [str(p) for p in assets if p]


def _goal_tokens(goal: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9_]{2,}", goal.lower()) if t not in _STOP]


def _scene_matches_goal_tokens(goal: str, snapshot: Any) -> bool:
    tokens = _goal_tokens(goal)
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


def spawn_asset_in_view(
    client: RemoteUeClient,
    asset_path: str,
    *,
    with_light: bool = True,
    force_skeletal: bool = False,
) -> list[dict[str, Any]]:
    """Direct spawn commands for a known /Game asset path (no LLM)."""
    asset_path = asset_path.strip()
    if not asset_path:
        return []
    view_res = client.command({"command": "world.get_view", "params": {}})
    loc = {"x": 0.0, "y": 0.0, "z": 150.0}
    if view_res.get("success"):
        try:
            inner = json.loads(view_res.get("result_json") or "{}")
            vloc = inner.get("location") or {}
            vfwd = inner.get("forward") or {"x": 1.0, "y": 0.0, "z": 0.0}
            dist = 400.0
            loc = {
                "x": float(vloc.get("x", 0)) + float(vfwd.get("x", 1)) * dist,
                "y": float(vloc.get("y", 0)) + float(vfwd.get("y", 0)) * dist,
                "z": float(vloc.get("z", 100)) + 50.0,
            }
        except json.JSONDecodeError:
            pass

    results: list[dict[str, Any]] = []
    if with_light:
        results.append(client.command({
            "command": "world.spawn_actor",
            "params": {
                "class_path": "/Script/Engine.PointLight",
                "transform": {
                    "location": {**loc, "z": loc["z"] + 120.0},
                    "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            },
        }))

    skel = (
        force_skeletal
        or "SkeletalMesh" in asset_path
        or asset_path.endswith(".SkeletalMesh")
        or "/SK_" in asset_path
    )
    if skel:
        results.append(client.command({
            "command": "animation.spawn_skeletal_mesh",
            "params": {
                "mesh_path": asset_path,
                "transform": {
                    "location": loc,
                    "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            },
        }))
        # If skeletal spawn fails (asset imported as StaticMesh), fall back.
        if results and not results[-1].get("success"):
            results.append(client.command({
                "command": "world.spawn_mesh",
                "params": {
                    "mesh_path": asset_path,
                    "transform": {
                        "location": loc,
                        "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            }))
    else:
        results.append(client.command({
            "command": "world.spawn_mesh",
            "params": {
                "mesh_path": asset_path,
                "transform": {
                    "location": loc,
                    "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                    "scale": {"x": 2.0, "y": 2.0, "z": 2.0},
                },
            },
        }))
    return results


def _rank_asset_paths(goal: str, paths: list[str]) -> list[str]:
    tokens = _goal_tokens(goal)
    if not tokens:
        return paths

    def score(path: str) -> int:
        blob = path.lower()
        return sum(2 if t in blob else 0 for t in tokens)

    return sorted(paths, key=score, reverse=True)


def augment_goal_with_assets(client: RemoteUeClient, goal: str) -> tuple[str, list[str], dict[str, Any]]:
    """
    Search /Game for tokens in the user goal.
    If exactly one mesh match for a token, rewrite goal to spawn that asset in view.
    """
    meta: dict[str, Any] = {"searches": [], "matches": []}
    tokens = _goal_tokens(goal)
    if not tokens:
        return goal, [], meta

    creature_hints = ("dog", "cat", "wolf", "horse", "human", "character", "creature", "animal", "beverly", "bill")
    wants_creature = any(h in goal.lower() for h in creature_hints)

    mesh_matches: list[str] = []
    for token in tokens[:4]:
        classes = ("SkeletalMesh", "StaticMesh", "") if wants_creature else ("", "SkeletalMesh", "StaticMesh")
        for asset_class in classes:
            paths = search_project_assets(client, token, asset_class=asset_class, limit=8)
            meta["searches"].append({"token": token, "class": asset_class, "count": len(paths)})
            for p in paths:
                # Never treat animations as spawnable mesh candidates.
                if ".AnimSequence" in p or ".AnimMontage" in p or "/Anims/" in p:
                    continue
                if p not in mesh_matches:
                    mesh_matches.append(p)

    anim_matches: list[str] = []
    anim_hints = ("walk", "run", "idle", "anim", "montage")
    if any(h in goal.lower() for h in anim_hints):
        for token in tokens[:3]:
            for asset_class in ("AnimSequence", "AnimMontage"):
                anims = search_project_assets(client, token, asset_class=asset_class, limit=6)
                for p in anims:
                    if p not in anim_matches:
                        anim_matches.append(p)

    mesh_matches = _rank_asset_paths(goal, mesh_matches)[:16]
    if wants_creature:
        skel = [
            p for p in mesh_matches
            if "SkeletalMesh" in p or p.endswith(".SkeletalMesh") or "/SK_" in p or "_SK." in p
        ]
        if skel:
            mesh_matches = skel + [p for p in mesh_matches if p not in skel]

    all_matches = list(mesh_matches) + [p for p in anim_matches if p not in mesh_matches]
    meta["matches"] = all_matches[:20]
    meta["mesh_matches"] = mesh_matches[:16]
    meta["anim_matches"] = anim_matches[:8]

    if len(mesh_matches) == 1:
        path = mesh_matches[0]
        if path.endswith((".SkeletalMesh",)) or "SkeletalMesh" in path or "/SK_" in path or "SK_" in path or "_SK." in path:
            augmented = (
                f"Spawn skeletal mesh {path} in front of the camera with a spotlight. "
                f"Original request: {goal}"
            )
        else:
            augmented = (
                f"Spawn static mesh {path} in front of the camera with a spotlight. "
                f"Original request: {goal}"
            )
        if anim_matches:
            augmented += f"\nCandidate animations: {'; '.join(anim_matches[:4])}"
        return augmented, all_matches, meta

    if mesh_matches or anim_matches:
        parts = [goal]
        if mesh_matches:
            parts.append(f"Candidate meshes: {'; '.join(mesh_matches[:8])}")
        if anim_matches:
            parts.append(f"Candidate animations: {'; '.join(anim_matches[:4])}")
        return "\n".join(parts), all_matches, meta

    return goal, [], meta
