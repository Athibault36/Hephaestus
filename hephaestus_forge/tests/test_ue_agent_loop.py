"""Tests for observe→act heuristic (no Unreal required)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ue_agent_loop import WorldSnapshot, decide_action, summarize_actors  # noqa: E402


def test_summarize_actors():
    paths = [
        "/Temp/...PointLight_0",
        "/Temp/...StaticMeshActor_1",
        "/Temp/...StaticMeshActor_2",
        "/Temp/...PlayerController_0",
    ]
    lights, meshes = summarize_actors(paths)
    assert lights == 1
    assert meshes == 2


def test_decide_seeds_light_first():
    snap = WorldSnapshot(lights=0, meshes=0)
    action = decide_action(snap, random.Random(0))
    assert action.kind == "spawn_light"
    assert action.command["command"] == "world.spawn_actor"


def test_decide_seeds_cube_after_light():
    snap = WorldSnapshot(lights=1, meshes=0)
    action = decide_action(snap, random.Random(0))
    assert action.kind == "spawn_cube"


def test_decide_noop_when_seeded():
    snap = WorldSnapshot(lights=2, meshes=3)
    action = decide_action(snap, random.Random(0))
    assert action.kind == "noop"


if __name__ == "__main__":
    test_summarize_actors()
    test_decide_seeds_light_first()
    test_decide_seeds_cube_after_light()
    test_decide_noop_when_seeded()
    print("OK")
