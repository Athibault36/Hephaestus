# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Tests for the world.get_actor verb (Python builder + schema, no Unreal)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PY = ROOT / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PLUGIN_PY))

from hephaestus.commands import build_get_actor_command, get_actor_json  # noqa: E402
from remote_command_schema import (  # noqa: E402
    assert_uses_params_key,
    resolve_params,
    validate_world_get_actor,
)


def test_builder_shape_and_params_key():
    payload = build_get_actor_command("/Temp/UEDPIE.PersistentLevel.StaticMeshActor_1")
    assert payload["command"] == "world.get_actor"
    assert_uses_params_key(payload)
    assert payload["params"]["actor_path"] == "/Temp/UEDPIE.PersistentLevel.StaticMeshActor_1"
    assert validate_world_get_actor(payload) == []


def test_builder_json_round_trip():
    restored = json.loads(get_actor_json("Foo"))
    assert restored["command"] == "world.get_actor"
    assert restored["params"]["actor_path"] == "Foo"


def test_validate_rejects_missing_and_blank_actor_path():
    assert validate_world_get_actor({"command": "world.get_actor", "params": {}}) != []
    assert validate_world_get_actor({"command": "world.get_actor", "params": {"actor_path": "  "}}) != []
    assert validate_world_get_actor({"command": "world.get_actor"}) == ["missing params/args object"]


def test_validate_rejects_wrong_command():
    errors = validate_world_get_actor({"command": "world.list_actors", "params": {"actor_path": "X"}})
    assert "command must be world.get_actor" in errors


def test_validate_accepts_args_alias():
    body = {"command": "world.get_actor", "args": {"actor_path": "/Temp/PointLight_0"}}
    assert validate_world_get_actor(body) == []
    assert resolve_params(body) == {"actor_path": "/Temp/PointLight_0"}


if __name__ == "__main__":
    test_builder_shape_and_params_key()
    test_builder_json_round_trip()
    test_validate_rejects_missing_and_blank_actor_path()
    test_validate_rejects_wrong_command()
    test_validate_accepts_args_alias()
    print("ok")
