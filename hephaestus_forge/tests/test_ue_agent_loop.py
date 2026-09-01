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
    lights, meshes, skeletal = summarize_actors(paths)
    assert lights == 1
    assert meshes == 2
    assert skeletal == 0


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


def test_decide_jog_goal():
    snap = WorldSnapshot(lights=2, meshes=3)
    action = decide_action(snap, random.Random(0), goal="make the character jog forward")
    assert action.kind == "apply_move"
    assert action.command["command"] == "world.apply_move_input"


def test_decide_frame_goal():
    snap = WorldSnapshot(
        lights=2,
        meshes=3,
        view={"location": {"x": 0, "y": 0, "z": 200}, "forward": {"x": 1, "y": 0, "z": 0}},
    )
    action = decide_action(snap, random.Random(0), goal="frame the character from the left")
    assert action.kind == "create_shot"
    assert action.command["command"] == "sequence.create_shot"


def test_decide_play_anim_when_skeletal_and_hint():
    skel = "/Temp/UEDPIE.PersistentLevel.SkeletalMeshActor_0"
    snap = WorldSnapshot(lights=2, meshes=1, skeletal=1, actor_paths=[skel])
    action = decide_action(
        snap,
        random.Random(0),
        goal="play run cycle on the dog",
        asset_hints=["/Game/Anims/Dog_Run.Dog_Run"],
    )
    assert action.kind == "play_anim"
    assert action.command["params"]["anim_path"] == "/Game/Anims/Dog_Run.Dog_Run"


if __name__ == "__main__":
    test_summarize_actors()
    test_decide_seeds_light_first()
    test_decide_seeds_cube_after_light()
    test_decide_noop_when_seeded()
    print("OK")
