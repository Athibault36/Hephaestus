"""Tests for command_id propagation through tool results and traces."""

from hephaestus_forge.runtime.llm import LLMResponse, ToolCall
from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.tracing import TraceRecorder
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


def test_tool_result_includes_command_id():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    result = reg.execute(ue, "world.query_spatial", {})
    assert result.success is True
    assert result.command_id.startswith("cmd_")
    assert result.to_summary()["command_id"] == result.command_id
    ue.close()


def test_trace_span_records_command_id():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    tracer = TraceRecorder(enabled=True)

    class OneShot:
        def chat(self, messages, tools=None):
            return LLMResponse(tool_calls=[ToolCall(id="1", name="world__query_spatial", arguments={})])

    runtime = AgentRuntime(OneShot(), ue, reg, max_steps=2, tracer=tracer)
    runtime.run("look")

    tool_spans = [s for s in tracer.spans if s.name == "agent.tool"]
    assert tool_spans
    assert tool_spans[0].attributes.get("command_id", "").startswith("cmd_")
    ue.close()
