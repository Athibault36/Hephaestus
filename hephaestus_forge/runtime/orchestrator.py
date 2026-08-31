"""Runtime agent orchestrator: the LLM -> tools -> UE loop.

This is the minimal "observe, think, act" loop that connects a reasoning LLM to
the running UE editor through the tool registry:

    observe (optional vision.capture_frame)
      -> think (LLM chooses tool calls)
        -> act (execute tools against UE)
          -> feed results back, repeat until the model answers with no tool call

It is deliberately small and synchronous. Swap in a fake ``LLM`` and a mocked
``UEClient`` to test the whole loop without an engine or GPU.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .llm import LLM, LLMResponse, extract_tool_calls_from_text
from .tools import ToolError, ToolRegistry, ToolResult
from .ue_client import UEClient, UEConnectionError

DEFAULT_SYSTEM_PROMPT = (
    "You are Hephaestus, an autonomous agent operating a live Unreal Engine 5.8 "
    "scene through a set of tools. Work toward the user's goal by calling tools. "
    "Observe the scene with vision.capture_frame when you need to see current "
    "state, then act with world.* tools. Call one or more tools per step. When the "
    "goal is fully achieved, reply with a short natural-language summary and DO NOT "
    "call any tool."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TrajectoryEvent:
    """A single step in the agent's trajectory (mirrors Mission Control's log)."""

    type: str  # observation | thought | action | tool_result | final | error
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class RunResult:
    goal: str
    completed: bool
    final_message: str
    steps: int
    trajectory: List[TrajectoryEvent] = field(default_factory=list)
    tool_calls: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "completed": self.completed,
            "final_message": self.final_message,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "trajectory": [e.to_dict() for e in self.trajectory],
        }


class AgentRuntime:
    """Drives an LLM through a tool-using loop against a UE bridge.

    Args:
        llm: Any object implementing the ``LLM`` protocol.
        ue_client: Connected :class:`UEClient`.
        registry: Tools the agent may call.
        system_prompt: System instructions for the model.
        max_steps: Hard cap on think/act iterations.
        observe_first: If True, capture a frame before the first thought so the
            model starts with an observation of the scene.
        on_event: Optional callback invoked for every :class:`TrajectoryEvent`
            (e.g. to stream into Mission Control).
    """

    def __init__(
        self,
        llm: LLM,
        ue_client: UEClient,
        registry: ToolRegistry,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = 12,
        observe_first: bool = False,
        on_event: Optional[Callable[[TrajectoryEvent], None]] = None,
        allow_text_tool_calls: bool = True,
    ):
        self.llm = llm
        self.ue = ue_client
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_steps = max(1, int(max_steps))
        self.observe_first = observe_first
        self.on_event = on_event
        # Recover tool calls from plain text for models without native tool-calling.
        self.allow_text_tool_calls = allow_text_tool_calls

    def _emit(self, trajectory: List[TrajectoryEvent], event: TrajectoryEvent) -> None:
        trajectory.append(event)
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:  # never let a UI callback break the loop
                pass

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> ToolResult:
        try:
            return self.registry.execute(self.ue, name, args)
        except ToolError as exc:
            return ToolResult(tool=name, success=False, error=str(exc))
        except UEConnectionError as exc:
            return ToolResult(tool=name, success=False, error=f"UE unreachable: {exc}")

    def run(self, goal: str) -> RunResult:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": goal},
        ]
        trajectory: List[TrajectoryEvent] = []
        tool_call_count = 0

        if self.observe_first:
            observation = self._execute_tool("vision.capture_frame", {})
            summary = observation.to_summary()
            self._emit(
                trajectory,
                TrajectoryEvent("observation", "Captured initial viewport frame", summary),
            )
            messages.append(
                {"role": "user", "content": f"Initial observation: {json.dumps(summary)}"}
            )

        tools = self.registry.openai_schemas()

        for step in range(1, self.max_steps + 1):
            response: LLMResponse = self.llm.chat(messages, tools=tools)

            native = bool(response.tool_calls)
            calls = list(response.tool_calls)
            if not calls and self.allow_text_tool_calls:
                calls = extract_tool_calls_from_text(response.content)

            if not calls:
                final = response.content or "(no final message)"
                self._emit(trajectory, TrajectoryEvent("final", final))
                return RunResult(
                    goal=goal,
                    completed=True,
                    final_message=final,
                    steps=step,
                    trajectory=trajectory,
                    tool_calls=tool_call_count,
                )

            if response.content:
                self._emit(trajectory, TrajectoryEvent("thought", response.content))

            if native:
                # OpenAI tool-calling protocol: assistant tool_calls + tool-role results.
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id or f"call_{step}_{i}",
                                "type": "function",
                                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                            }
                            for i, tc in enumerate(calls)
                        ],
                    }
                )
            else:
                # Text-parsed tool calls: keep the raw assistant turn as context.
                messages.append({"role": "assistant", "content": response.content or ""})

            observations = []
            for i, call in enumerate(calls):
                tool_call_count += 1
                self._emit(
                    trajectory,
                    TrajectoryEvent("action", f"{call.name}({json.dumps(call.arguments)})", {"tool": call.name}),
                )
                result = self._execute_tool(call.name, call.arguments)
                summary = result.to_summary()
                self._emit(
                    trajectory,
                    TrajectoryEvent(
                        "tool_result" if result.success else "error",
                        f"{call.name} -> {'ok' if result.success else result.error}",
                        summary,
                    ),
                )
                if native:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id or f"call_{step}_{i}",
                            "name": call.name,
                            "content": json.dumps(summary),
                        }
                    )
                else:
                    observations.append({"tool": call.name, "result": summary})

            if not native:
                # Feed results back as a user turn for plain chat models.
                messages.append(
                    {"role": "user", "content": f"Tool results: {json.dumps(observations)}"}
                )

        # Ran out of steps without a final answer.
        self._emit(trajectory, TrajectoryEvent("error", f"Reached max_steps={self.max_steps} without completion"))
        return RunResult(
            goal=goal,
            completed=False,
            final_message="Stopped: reached step limit before the goal was reported complete.",
            steps=self.max_steps,
            trajectory=trajectory,
            tool_calls=tool_call_count,
        )
