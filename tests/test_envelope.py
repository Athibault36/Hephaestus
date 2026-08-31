"""Tests for command envelope structural validation."""

from hephaestus_forge.runtime.envelope import load_command_envelope_schema, validate_command_envelope
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


def test_schema_file_loads():
    schema = load_command_envelope_schema()
    assert schema["required"] == ["command", "params"]


def test_validate_command_envelope_accepts_tool_output():
    reg = build_default_registry()
    tool = reg.get("world.spawn_actor")
    command, params = tool.builder({"class_path": "/Script/Engine.StaticMeshActor"})
    ok, err = validate_command_envelope({"command": command, "params": params})
    assert ok is True, err


def test_validate_command_envelope_rejects_missing_params():
    ok, err = validate_command_envelope({"command": "world.spawn_actor"})
    assert ok is False
    assert "params" in err


def test_all_core_tools_produce_valid_envelopes():
    fake = FakeUE()
    client = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    samples = {
        "world.spawn_actor": {"class_path": "/Script/Engine.StaticMeshActor"},
        "world.destroy_actor": {"actor_path": "/Game/L.L:PersistentLevel.Cube_1"},
        "world.query_spatial": {},
        "world.batch_edit": {"actors": ["/Game/L.L:PersistentLevel.Cube_1"]},
        "vision.capture_frame": {},
    }
    for name, args in samples.items():
        tool = reg.get(name)
        command, params = tool.builder(args)
        ok, err = validate_command_envelope({"command": command, "params": params})
        assert ok, f"{name}: {err}"
        result = reg.execute(client, name, args)
        assert result.success, result.error
    client.close()
