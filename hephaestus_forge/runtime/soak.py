"""Repeated agent run helper for soak testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .orchestrator import AgentRuntime, RunResult


@dataclass
class SoakRun:
    index: int
    completed: bool
    steps: int
    tool_calls: int
    final_message: str

    @classmethod
    def from_result(cls, index: int, result: "RunResult") -> "SoakRun":
        return cls(
            index=index,
            completed=result.completed,
            steps=result.steps,
            tool_calls=result.tool_calls,
            final_message=result.final_message,
        )


def run_soak(runtime: "AgentRuntime", goal: str, *, repeat: int = 1) -> List[SoakRun]:
    """Run the agent *repeat* times; returns one summary row per iteration."""
    repeat = max(1, int(repeat))
    runs: List[SoakRun] = []
    for i in range(repeat):
        label = goal if repeat == 1 else f"{goal} (run {i + 1}/{repeat})"
        result = runtime.run(label)
        runs.append(SoakRun.from_result(i + 1, result))
    return runs
