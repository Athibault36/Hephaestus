"""Tests for vision LLM plan parsing (no network / no Unreal required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ue_agent_loop import WorldSnapshot  # noqa: E402
from ue_vision_planner import _extract_json_object, plan_dict_to_action  # noqa: E402


def test_extract_json_from_fences():
    raw = '```json\n{"action":"noop","reason":"done"}\n```'
    obj = _extract_json_object(raw)
    assert obj["action"] == "noop"


def test_plan_spawn_cube():
    snap = WorldSnapshot(lights=1, meshes=0, actor_paths=[])
    action = plan_dict_to_action(
        {"action": "spawn_cube", "reason": "need cube", "x": 10, "y": -20, "z": 100},
        snap,
    )
    assert action.kind == "spawn_cube"
    assert action.command["command"] == "world.spawn_mesh"
    assert action.command["params"]["transform"]["location"]["x"] == 10.0


def test_plan_destroy_rejects_unknown_path():
    snap = WorldSnapshot(actor_paths=["/Temp/PointLight_0"])
    action = plan_dict_to_action(
        {"action": "destroy", "reason": "cleanup", "actor_path": "/Temp/DoesNotExist"},
        snap,
    )
    assert action.kind == "noop"


def test_plan_destroy_accepts_listed_mesh():
    path = "/Temp/UEDPIE.PersistentLevel.StaticMeshActor_1"
    snap = WorldSnapshot(actor_paths=[path])
    action = plan_dict_to_action(
        {"action": "destroy", "reason": "remove cube", "actor_path": path},
        snap,
    )
    assert action.kind == "destroy"
    assert action.command["params"]["actor_path"] == path


def test_plan_set_transform_and_light():
    path = "/Temp/PersistentLevel.PointLight_0"
    mesh = "/Temp/PersistentLevel.StaticMeshActor_1"
    snap = WorldSnapshot(actor_paths=[path, mesh], lights=1, meshes=1)
    move = plan_dict_to_action(
        {"action": "set_transform", "actor_path": mesh, "x": 50, "y": 0, "z": 120, "reason": "nudge"},
        snap,
    )
    assert move.kind == "set_transform"
    light = plan_dict_to_action(
        {"action": "set_light", "actor_path": path, "intensity": 9000, "reason": "brighter"},
        snap,
    )
    assert light.kind == "set_light"
    assert light.command["params"]["intensity"] == 9000.0


if __name__ == "__main__":
    test_extract_json_from_fences()
    test_plan_spawn_cube()
    test_plan_destroy_rejects_unknown_path()
    test_plan_destroy_accepts_listed_mesh()
    test_plan_set_transform_and_light()
    print("OK")
