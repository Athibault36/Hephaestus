"""Unit tests for Hephaestus command JSON builders (no Unreal required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow importing plugin Python package from template
ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PY = ROOT / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"
sys.path.insert(0, str(PLUGIN_PY))

from hephaestus.commands import (  # noqa: E402
    build_capture_frame_command,
    build_destroy_actor_command,
    build_list_actors_command,
    build_set_view_command,
    build_sequence_create_shot_command,
    build_spawn_actor_command,
    build_spawn_mesh_command,
)


def test_spawn_actor_command_shape():
    payload = build_spawn_actor_command(
        class_path="/Script/Engine.PointLight",
        location=(100.0, 200.0, 50.0),
        rotation=(0.0, 45.0, 0.0),
        scale=(1.0, 1.0, 1.0),
    )
    assert payload["command"] == "world.spawn_actor"
    assert payload["params"]["class_path"] == "/Script/Engine.PointLight"
    assert payload["params"]["transform"]["location"] == {"x": 100.0, "y": 200.0, "z": 50.0}
    assert payload["params"]["transform"]["rotation"] == {"pitch": 0.0, "yaw": 45.0, "roll": 0.0}
    # Must be valid JSON round-trip for C++ parser
    restored = json.loads(json.dumps(payload))
    assert restored["command"] == "world.spawn_actor"


def test_spawn_actor_defaults_identity_transform():
    payload = build_spawn_actor_command(class_path="/Script/Engine.StaticMeshActor")
    t = payload["params"]["transform"]
    assert t["location"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert t["scale"] == {"x": 1.0, "y": 1.0, "z": 1.0}


def test_spawn_mesh_and_vision_builders():
    mesh = build_spawn_mesh_command(location=(1, 2, 3))
    assert mesh["command"] == "world.spawn_mesh"
    assert mesh["params"]["mesh_path"] == "/Engine/BasicShapes/Cube.Cube"
    assert build_destroy_actor_command("Foo")["params"]["actor_path"] == "Foo"
    assert build_list_actors_command()["command"] == "world.list_actors"
    assert build_capture_frame_command()["command"] == "vision.capture_frame"


def test_set_view_and_create_shot_builders():
    view = build_set_view_command(
        look_at_actor="/Game/Maps/M.M:PersistentLevel.Char",
        distance=450.0,
        yaw_offset=90.0,
        mode="free",
    )
    assert view["command"] == "world.set_view"
    assert view["params"]["mode"] == "free"
    assert view["params"]["look_at_actor"].endswith("Char")
    assert view["params"]["distance"] == 450.0

    shot = build_sequence_create_shot_command(
        look_at_actor="/Temp/A",
        distance=400.0,
        yaw_offset=-90.0,
        duration=2.0,
    )
    assert shot["command"] == "sequence.create_shot"
    assert shot["params"]["mode"] == "free"
    assert shot["params"]["yaw_offset"] == -90.0


if __name__ == "__main__":
    test_spawn_actor_command_shape()
    test_spawn_actor_defaults_identity_transform()
    test_spawn_mesh_and_vision_builders()
    test_set_view_and_create_shot_builders()
    print("OK")
