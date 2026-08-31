"""End-to-end tests for the LLM -> tools -> UE loop using a scripted fake LLM."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hephaestus_forge.runtime.llm import LLMResponse, ToolCall
from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


class ScriptedLLM:
    """Returns a predefined sequence of LLMResponses, one per chat() call."""

    def __init__(self, script: List[LLMResponse]):
        self.script = script
        self.calls: List[Dict[str, Any]] = []

    def chat(self, messages, tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        idx = min(len(self.calls) - 1, len(self.script) - 1)
        return self.script[idx]


def make_ue(fake: FakeUE) -> UEClient:
    return UEClient(base_url="http://ue.test", transport=make_transport(fake))


def test_observe_think_act_then_finish():
    fake = FakeUE()
    ue = make_ue(fake)
    registry = build_default_registry()

    script = [
        # Step 1: spawn a cube.
        LLMResponse(
            content="Spawning a cube at the origin.",
            tool_calls=[ToolCall(id="c1", name="world.spawn_actor",
                                 arguments={"class_path": "/Script/Engine.StaticMeshActor"})],
        ),
        # Step 2: no tool calls -> final answer.
        LLMResponse(content="Done: spawned one actor."),
    ]
    llm = ScriptedLLM(script)

    events: List[str] = []
    runtime = AgentRuntime(llm, ue, registry, max_steps=5, on_event=lambda e: events.append(e.type))
    result = runtime.run("Place a cube in the scene")

    assert result.completed is True
    assert result.tool_calls == 1
    assert "spawned one actor" in result.final_message
    assert fake.spawn_counter == 1
    # Trajectory captured a thought, an action, a tool_result, and a final.
    assert "action" in events and "tool_result" in events and "final" in events
    # Second LLM turn saw the tool result in its message history.
    assert any(m.get("role") == "tool" for m in llm.calls[1]["messages"])


def test_observe_first_captures_frame_before_thinking():
    fake = FakeUE()
    ue = make_ue(fake)
    registry = build_default_registry()
    llm = ScriptedLLM([LLMResponse(content="Nothing to do.")])

    runtime = AgentRuntime(llm, ue, registry, observe_first=True, max_steps=3)
    result = runtime.run("Look around")

    assert result.completed is True
    assert fake.frame_counter == 1  # a frame was captured before the first thought
    assert result.trajectory[0].type == "observation"


def test_tool_failure_is_fed_back_and_recovers():
    fake = FakeUE()
    ue = make_ue(fake)
    registry = build_default_registry()

    script = [
        # First attempt: invalid spawn (missing class_path) -> tool error surfaced.
        LLMResponse(tool_calls=[ToolCall(id="c1", name="world.spawn_actor", arguments={})]),
        # Recover: valid spawn.
        LLMResponse(tool_calls=[ToolCall(id="c2", name="world.spawn_actor",
                                         arguments={"class_path": "/Script/Engine.StaticMeshActor"})]),
        # Finish.
        LLMResponse(content="Recovered and spawned the actor."),
    ]
    llm = ScriptedLLM(script)
    runtime = AgentRuntime(llm, ue, registry, max_steps=6)
    result = runtime.run("Spawn something, recover from errors")

    assert result.completed is True
    assert result.tool_calls == 2
    error_events = [e for e in result.trajectory if e.type == "error"]
    assert error_events and "class_path" in error_events[0].metadata.get("error", "")
    assert fake.spawn_counter == 1


def test_text_tool_call_fallback_for_non_native_models():
    fake = FakeUE()
    ue = make_ue(fake)
    registry = build_default_registry()

    # Model emits a JSON tool directive in content (no native tool_calls).
    script = [
        LLMResponse(content='{"tool": "world.spawn_actor", "args": {"class_path": "/Script/Engine.StaticMeshActor"}}'),
        LLMResponse(content="Spawned it."),
    ]
    llm = ScriptedLLM(script)
    runtime = AgentRuntime(llm, ue, registry, max_steps=5)
    result = runtime.run("spawn via text tool call")

    assert result.completed is True
    assert result.tool_calls == 1
    assert fake.spawn_counter == 1
    # Results were fed back as a user turn (plain-chat protocol).
    assert any(m.get("role") == "user" and "Tool results" in m.get("content", "")
               for m in llm.calls[1]["messages"])


def test_max_steps_bound_when_model_never_finishes():
    fake = FakeUE()
    ue = make_ue(fake)
    registry = build_default_registry()
    # Always calls a tool, never finishes.
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[ToolCall(id="c", name="vision.capture_frame", arguments={})])
    ])
    runtime = AgentRuntime(llm, ue, registry, max_steps=3)
    result = runtime.run("loop forever")

    assert result.completed is False
    assert result.steps == 3
    assert result.tool_calls == 3
