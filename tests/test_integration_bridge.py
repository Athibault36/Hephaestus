"""Integration-style tests: full agent loop against fake UE with extended tools + auth."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from hephaestus_forge.runtime.llm import LLMResponse, ToolCall
from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient, UEConnectionError
from tests.fake_ue import FakeUE, make_transport


class ScriptedLLM:
    def __init__(self, script: List[LLMResponse]):
        self.script = script
        self.calls = 0

    def chat(self, messages, tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        idx = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return self.script[idx]


def test_extended_tool_loop_with_auth():
    fake = FakeUE(require_auth=True, auth_token="integration")
    ue = UEClient(
        base_url="http://ue.test",
        transport=make_transport(fake),
        auth_token="integration",
    )
    registry = build_default_registry()

    script = [
        LLMResponse(
            content="Compile blueprint.",
            tool_calls=[
                ToolCall(
                    id="t1",
                    name="blueprint__compile",
                    arguments={"blueprint_path": "/Game/BP/BP_Hero.BP_Hero"},
                )
            ],
        ),
        LLMResponse(content="Blueprint compile requested."),
    ]
    runtime = AgentRuntime(ScriptedLLM(script), ue, registry, max_steps=4)
    result = runtime.run("Compile the hero blueprint")

    assert result.completed is True
    assert result.tool_calls == 1
    assert fake.received[-1]["command"] == "blueprint.compile"
    ue.close()


def test_capture_frame_and_fetch_png_with_auth():
    fake = FakeUE(require_auth=True, auth_token="secret")
    ue = UEClient(
        base_url="http://ue.test",
        transport=make_transport(fake),
        auth_token="secret",
    )
    cmd_result, png = ue.capture_frame(include_image=True)
    assert cmd_result.success is True
    assert png and png.startswith(b"\x89PNG")
    ue.close()


def test_batch_edit_tool_executes():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    result = reg.execute(
        ue,
        "world.batch_edit",
        {"actors": ["/Game/L.L:PersistentLevel.Cube_1"], "operation": "set_location", "location": [0, 0, 100]},
    )
    assert result.success is True
    assert fake.received[-1]["command"] == "world.batch_edit"
    ue.close()


def test_spawn_validation_rejects_bad_class_path():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    result = reg.execute(ue, "world.spawn_actor", {"class_path": "evil/path"})
    assert result.success is False
    assert result.error_kind == "validation"
    assert result.error_code == "VALIDATION_SPAWN_CLASS_DENIED"
    assert not fake.received
    ue.close()


def test_auth_failure_surfaces_as_auth_error():
    fake = FakeUE(require_auth=True, auth_token="good")
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake), auth_token="bad")
    with pytest.raises(UEConnectionError) as exc:
        ue.health()
    assert exc.value.info.kind.value == "auth"
    ue.close()


def test_metrics_recorded_during_agent_loop():
    from hephaestus_forge.runtime.metrics import MetricsRegistry

    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    metrics = MetricsRegistry()
    script = [
        LLMResponse(
            tool_calls=[ToolCall(id="1", name="world__query_spatial", arguments={})],
        ),
        LLMResponse(content="Done."),
    ]
    runtime = AgentRuntime(ScriptedLLM(script), ue, reg, max_steps=3, metrics=metrics)
    runtime.run("query scene")

    text = metrics.render()
    assert "hephaestus_tool_calls_total" in text
    assert "hephaestus_agent_loop_steps_total" in text
    ue.close()
