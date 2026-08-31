"""Tests for structured error taxonomy."""

import pytest

from hephaestus_forge.runtime.errors import ErrorKind, ToolError, auth_error, infer_command_error, validation_error
from hephaestus_forge.runtime.orchestrator import AgentRuntime, TrajectoryEvent
from hephaestus_forge.runtime.tools import ToolResult, build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient, UEConnectionError
from tests.fake_ue import FakeUE, make_transport


def test_tool_error_carries_validation_kind():
    err = ToolError("missing class_path")
    assert err.info.kind == ErrorKind.VALIDATION
    assert err.info.code == "TOOL_INVALID_ARGS"


def test_tool_result_failure_includes_kind():
    info = validation_error("MISSING_FIELD", "bad args")
    result = ToolResult.failure("world.spawn_actor", info)
    summary = result.to_summary()
    assert summary["error_kind"] == "validation"
    assert summary["error_code"] == "MISSING_FIELD"


def test_ue_connection_error_auth():
    exc = UEConnectionError("nope", code="BRIDGE_UNAUTHORIZED", info=auth_error("BRIDGE_UNAUTHORIZED", "nope"))
    assert exc.info.kind == ErrorKind.AUTH


def test_infer_command_error_transport():
    info = infer_command_error("Failed to reach UE bridge: timeout")
    assert info.kind == ErrorKind.TRANSPORT


def test_orchestrator_surfaces_tool_validation_error():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()

    class OneShotLLM:
        def chat(self, messages, tools=None):
            from hephaestus_forge.runtime.llm import LLMResponse, ToolCall

            return LLMResponse(
                tool_calls=[ToolCall(id="1", name="world__spawn_actor", arguments={})]
            )

    events: list[TrajectoryEvent] = []
    runtime = AgentRuntime(OneShotLLM(), ue, reg, max_steps=2, on_event=lambda e: events.append(e))
    runtime.run("spawn")

    error_events = [e for e in events if e.type == "error"]
    assert error_events
    assert error_events[0].metadata.get("error_kind") == "validation"
    ue.close()


def test_ue_client_auth_maps_to_error_kind():
    fake = FakeUE(require_auth=True, auth_token="secret")
    client = UEClient(base_url="http://ue.test", transport=make_transport(fake), auth_token="bad")
    with pytest.raises(UEConnectionError) as exc:
        client.health()
    assert exc.value.info.kind == ErrorKind.AUTH
    client.close()
