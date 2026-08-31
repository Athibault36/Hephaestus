"""Tests for tracing stub."""

from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.tracing import TraceRecorder
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


def test_trace_recorder_records_spans():
    tracer = TraceRecorder(enabled=True, endpoint="http://127.0.0.1:4318/v1/traces")
    with tracer.span("test.span", foo="bar") as span:
        assert span.name == "test.span"
        assert span.attributes["foo"] == "bar"
    assert len(tracer.spans) == 1
    assert tracer.spans[0].duration_ms is not None
    tracer.close()


def test_orchestrator_emits_trace_spans():
    from hephaestus_forge.runtime.llm import LLMResponse, ToolCall

    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    tracer = TraceRecorder(enabled=True)

    class OneShotLLM:
        def chat(self, messages, tools=None):
            return LLMResponse(
                tool_calls=[ToolCall(id="1", name="world__query_spatial", arguments={})],
            )

    runtime = AgentRuntime(OneShotLLM(), ue, reg, max_steps=2, tracer=tracer)
    runtime.run("look")

    names = [s.name for s in tracer.spans]
    assert "agent.step" in names
    assert "agent.tool" in names
    ue.close()
