# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PY = ROOT / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PLUGIN_PY))

from hephaestus.commands import build_spawn_mesh_command  # noqa: E402
from remote_command_schema import (  # noqa: E402
    assert_uses_params_key,
    parse_location,
    parse_scale,
    resolve_params,
    validate_animation_play_montage,
    validate_animation_play_locomotion,
    validate_asset_create_instance,
    validate_asset_create_material,
    validate_asset_export,
    validate_asset_import,
    validate_asset_search,
    validate_audio_create_metasound,
    validate_audio_synthesize,
    validate_sequence_create_shot,
    validate_sequence_play,
    validate_world_apply_move_input,
    validate_world_get_actor,
    validate_world_spawn_mesh,
)


def test_resolve_params_prefers_params_over_args():
    obj = {"command": "world.spawn_mesh", "params": {"a": 1}, "args": {"a": 2}}
    assert resolve_params(obj) == {"a": 1}


def test_resolve_params_falls_back_to_args():
    obj = {"command": "world.spawn_mesh", "args": {"mesh": "Cube"}}
    assert resolve_params(obj) == {"mesh": "Cube"}


def test_resolve_params_missing_is_none_not_empty():
    assert resolve_params({"command": "world.list_actors"}) is None


def test_parse_location_nested_and_flat_array():
    nested = {
        "transform": {
            "location": {"x": -700.0, "y": 0.0, "z": 100.0},
            "scale": {"x": 2, "y": 2, "z": 2},
        }
    }
    assert parse_location(nested) == (-700.0, 0.0, 100.0)
    flat = {"location": [-777.0, 55.0, 133.0], "scale": [5, 5, 5]}
    assert parse_location(flat) == (-777.0, 55.0, 133.0)
    assert parse_scale(flat) == (5.0, 5.0, 5.0)


def test_python_builder_emits_params():
    payload = build_spawn_mesh_command(location=(1.0, 2.0, 3.0))
    assert_uses_params_key(payload)
    assert validate_world_spawn_mesh(payload) == []
    assert parse_location(payload["params"]) == (1.0, 2.0, 3.0)


def test_validate_world_get_actor_requires_path():
    assert validate_world_get_actor({"command": "world.get_actor", "params": {}}) == [
        "missing actor_path"
    ]
    assert validate_world_get_actor({
        "command": "world.get_actor",
        "params": {"actor_path": "/Game/Maps/UEDPIE_0_Level.Level:PersistentLevel.StaticMeshActor_0"},
    }) == []


def test_args_only_client_still_resolves():
    body = {
        "command": "world.spawn_mesh",
        "args": {
            "mesh": "/Engine/BasicShapes/Cube.Cube",
            "location": [-500, 0, 120],
            "scale": [4, 4, 4],
        },
    }
    assert validate_world_spawn_mesh(body) == []
    params = resolve_params(body)
    assert params is not None
    assert parse_location(params) == (-500.0, 0.0, 120.0)


def test_validate_apply_move_and_montage():
    assert validate_world_apply_move_input({
        "command": "world.apply_move_input",
        "params": {"forward": 1.0, "duration": 2.0},
    }) == []
    assert validate_animation_play_montage({
        "command": "animation.play_montage",
        "params": {"actor_path": "/Temp/A", "montage_path": "/Game/M.Run"},
    }) == []
    assert "missing montage_path" in validate_animation_play_montage({
        "command": "animation.play_montage",
        "params": {"actor_path": "/Temp/A"},
    })
    assert validate_animation_play_locomotion({
        "command": "animation.play_locomotion",
        "params": {"actor_path": "/Temp/A", "mode": "idle"},
    }) == []


def test_validate_sequence_play_and_create_shot():
    assert validate_sequence_play({"command": "sequence.play", "params": {}}) == ["missing sequence_path"]
    assert validate_sequence_play({
        "command": "sequence.play",
        "params": {"sequence_path": "/Game/Seq.Intro"},
    }) == []
    assert validate_sequence_create_shot({
        "command": "sequence.create_shot",
        "params": {"location": {"x": 1, "y": 2, "z": 3}},
    }) == []


def test_validate_asset_commands():
    assert validate_asset_search({"command": "asset.search", "params": {}}) == ["missing query"]
    assert validate_asset_search({
        "command": "asset.search",
        "params": {"query": "dog", "limit": 5},
    }) == []
    assert validate_asset_create_material({
        "command": "asset.create_material",
        "params": {"name": "ProbeMat"},
    }) == []
    assert validate_asset_export({
        "command": "asset.export",
        "params": {"asset_path": "/Game/Mesh.Mesh"},
    }) == []
    assert "missing asset_path" in validate_asset_export({
        "command": "asset.export",
        "params": {},
    })
    assert validate_asset_import({
        "command": "asset.import",
        "params": {"file_path": "C:/tmp/mesh.fbx", "destination_path": "/Game/Imports"},
    }) == []
    missing = validate_asset_import({"command": "asset.import", "params": {"file_path": "x.fbx"}})
    assert "missing destination_path" in missing


def test_validate_audio_and_instance_commands():
    assert validate_asset_create_instance({
        "command": "asset.create_instance",
        "params": {},
    }) == []
    assert validate_audio_create_metasound({
        "command": "audio.create_metasound",
        "params": {"name": "Probe"},
    }) == []
    assert validate_audio_synthesize({
        "command": "audio.synthesize",
        "params": {"sound_path": "/Engine/EditorSounds/Notifications/CompileSuccess.CompileSuccess"},
    }) == []
    assert "missing sound_path" in validate_audio_synthesize({
        "command": "audio.synthesize",
        "params": {},
    })


if __name__ == "__main__":
    test_resolve_params_prefers_params_over_args()
    test_resolve_params_falls_back_to_args()
    test_resolve_params_missing_is_none_not_empty()
    test_parse_location_nested_and_flat_array()
    test_python_builder_emits_params()
    test_args_only_client_still_resolves()
    print("ok")
