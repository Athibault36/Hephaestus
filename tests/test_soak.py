"""Soak-style tests: repeated agent loops against FakeUE without hangs."""

from __future__ import annotations

from hephaestus_forge.runtime.llm import LLMResponse, ToolCall
from hephaestus_forge.runtime.metrics import MetricsRegistry
from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.tracing import TraceRecorder
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


class CyclingLLM:
    """Alternates tool call then finish."""

    def __init__(self, tool_name: str = "world__query_spatial"):
        self.tool_name = tool_name
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls % 2 == 1:
            return LLMResponse(tool_calls=[ToolCall(id=f"c{self.calls}", name=self.tool_name, arguments={})])
        return LLMResponse(content="done")


def test_repeated_agent_loops_complete():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    metrics = MetricsRegistry()
    tracer = TraceRecorder(enabled=True)

    for i in range(8):
        runtime = AgentRuntime(
            CyclingLLM(),
            ue,
            reg,
            max_steps=4,
            metrics=metrics,
            tracer=tracer,
        )
        result = runtime.run(f"goal-{i}")
        assert result.completed is True
        assert result.tool_calls >= 1

    assert fake.command_counter >= 8
    assert "hephaestus_tool_calls_total" in metrics.render()
    assert len(tracer.spans) >= 16
    ue.close()


def test_spawn_validation_consistent_across_python_and_fake_ue():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()

    py_result = reg.execute(ue, "world.spawn_actor", {"class_path": "evil/path"})
    assert py_result.success is False
    assert not fake.received

    direct = ue.execute("world.spawn_actor", {"action": "spawn_actor", "class_path": "evil/path"})
    assert direct.success is False
    assert "prefix denied" in direct.error_message.lower() or "denied" in direct.error_message.lower()
    ue.close()
