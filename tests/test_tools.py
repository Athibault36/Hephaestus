import pytest

from hephaestus_forge.runtime.tools import (
    ToolError,
    build_default_registry,
)
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


def make_client(fake: FakeUE) -> UEClient:
    return UEClient(base_url="http://ue.test", transport=make_transport(fake))


def test_spawn_actor_builds_full_transform_envelope():
    reg = build_default_registry()
    tool = reg.get("world.spawn_actor")
    command, params = tool.builder(
        {"class_path": "/Game/BP/BP_Cube.BP_Cube_C", "location": [100, 200, 300], "scale": 2}
    )
    assert command == "world.spawn_actor"
    assert params["action"] == "spawn_actor"
    assert params["transform"]["location"] == {"x": 100.0, "y": 200.0, "z": 300.0}
    assert params["transform"]["rotation"] == {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
    assert params["transform"]["scale"] == {"x": 2.0, "y": 2.0, "z": 2.0}


def test_spawn_actor_requires_class_path():
    reg = build_default_registry()
    with pytest.raises(ToolError):
        reg.get("world.spawn_actor").builder({"location": [0, 0, 0]})


def test_capture_frame_minimal_envelope():
    reg = build_default_registry()
    command, params = reg.get("vision.capture_frame").builder({})
    assert command == "vision.capture_frame"
    assert params == {"action": "capture_frame"}


def test_registry_execute_against_fake_ue():
    fake = FakeUE()
    client = make_client(fake)
    reg = build_default_registry()

    spawn = reg.execute(client, "world.spawn_actor", {"class_path": "/Script/Engine.StaticMeshActor"})
    assert spawn.success is True
    assert spawn.actor_references and "SpawnedActor_1" in spawn.actor_references[0]

    frame = reg.execute(client, "vision.capture_frame", {})
    assert frame.success is True
    assert frame.data["width"] == 1920


def test_openai_schemas_cover_all_tools_and_use_safe_names():
    reg = build_default_registry()
    schemas = reg.openai_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "world__spawn_actor" in names  # dots replaced for schema safety
    assert len(schemas) == 26


def test_registry_alias_lookup():
    reg = build_default_registry()
    # LLM-safe alias resolves back to the dotted tool.
    assert reg.get("world__spawn_actor").name == "world.spawn_actor"
    with pytest.raises(ToolError):
        reg.get("does.not.exist")
