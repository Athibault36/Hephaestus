import pytest

from hephaestus_forge.runtime.tools import ToolError, build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


def make_client(fake: FakeUE) -> UEClient:
    return UEClient(base_url="http://ue.test", transport=make_transport(fake))


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("asset.import", {"file_path": "/tmp/mesh.fbx", "destination_path": "/Game/Meshes"}),
        ("blueprint.compile", {"blueprint_path": "/Game/BP/BP_Hero.BP_Hero"}),
        ("rendering.dispatch_compute", {"shader_path": "/Game/Shaders/CS_Main"}),
        ("pcg.mutate_graph", {"graph_path": "/Game/PCG/ForestGraph"}),
        ("animation.edit_sequence", {"sequence_path": "/Game/Cinematics/Intro"}),
        ("audio.play_quartz", {"clock_name": "MainClock"}),
    ],
)
def test_extended_tools_build_and_execute(tool_name, args):
    fake = FakeUE()
    client = make_client(fake)
    reg = build_default_registry()
    result = reg.execute(client, tool_name, args)
    assert result.success is True
    assert fake.received[-1]["command"] == tool_name
    client.close()


def test_extended_registry_count():
    reg = build_default_registry()
    assert len(reg.names()) == 27


def test_build_without_extended():
    reg = build_default_registry(include_extended=False)
    assert len(reg.names()) == 5


def test_blueprint_compile_requires_valid_game_path():
    reg = build_default_registry()
    with pytest.raises(ToolError):
        reg.get("blueprint.compile").builder({"blueprint_path": "/tmp/evil.uasset"})
