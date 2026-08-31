"""Tests for command argument validation."""

import pytest

from hephaestus_forge.runtime.errors import ToolError
from hephaestus_forge.runtime.validation import (
    validate_actor_path,
    validate_actor_path_list,
    validate_spawn_class_path,
    validate_unreal_asset_path,
)


def test_spawn_class_path_accepts_script_prefix():
    assert validate_spawn_class_path("/Script/Engine.StaticMeshActor").startswith("/Script/")


def test_spawn_class_path_rejects_traversal():
    with pytest.raises(ToolError) as exc:
        validate_spawn_class_path("evil/path")
    assert exc.value.info.code == "VALIDATION_SPAWN_CLASS_DENIED"


def test_actor_path_rejects_parent_segments():
    with pytest.raises(ToolError) as exc:
        validate_actor_path("/Game/../Secret.Actor")
    assert exc.value.info.code == "VALIDATION_INVALID_PATH"


def test_unreal_asset_path_requires_game_prefix():
    with pytest.raises(ToolError):
        validate_unreal_asset_path("/tmp/mesh.fbx", "file_path", "asset.import")
    path = validate_unreal_asset_path("/Game/BP/BP_Hero.BP_Hero", "blueprint_path", "blueprint.compile")
    assert path.startswith("/Game/")


def test_actor_path_list_requires_non_empty():
    with pytest.raises(ToolError):
        validate_actor_path_list([])
