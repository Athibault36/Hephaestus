"""Wire recognized speech to the agent: hear the operator -> act.

A :class:`VoiceAgentSession` connects the always-on voice pipeline to the agent
runtime: when the enrolled operator speaks, the transcript becomes an agent goal;
when anyone else speaks, it is ignored. Optionally reports state to Mission
Control (speaker recognized/ignored + the heard command).

Kept transport-agnostic and synchronous so it is unit-testable with a fake
pipeline source, a fake runtime, and a fake bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np

from ..orchestrator import TrajectoryEvent
from .pipeline import RealtimeVoicePipeline, UtteranceEvent


@dataclass
class VoiceCommand:
    text: str
    similarity: float
    result: Any = None  # RunResult from the agent, if auto_run


class VoiceAgentSession:
    """Route operator utterances to the agent; ignore other speakers.

    Args:
        pipeline: The always-on voice pipeline (its callbacks are taken over here).
        runtime: An object with ``run(goal: str)`` (e.g. AgentRuntime).
        bridge: Optional MissionBridge to report speaker/command state.
        auto_run: When True, run the agent for each recognized command.
    """

    def __init__(self, pipeline: RealtimeVoicePipeline, runtime: Any, bridge: Any = None, auto_run: bool = True):
        self.pipeline = pipeline
        self.runtime = runtime
        self.bridge = bridge
        self.auto_run = auto_run
        self.history: List[VoiceCommand] = []
        self.ignored_count = 0

        # Take over the pipeline's callbacks.
        pipeline.on_utterance = self._on_operator
        pipeline.on_event = self._on_event
        if pipeline.on_speech_start is None:
            pipeline.on_speech_start = self._on_speech_start

    def feed_frame(self, frame: np.ndarray) -> Optional[UtteranceEvent]:
        return self.pipeline.process_frame(frame)

    def feed(self, frames: List[np.ndarray]) -> Optional[UtteranceEvent]:
        last: Optional[UtteranceEvent] = None
        for f in frames:
            r = self.pipeline.process_frame(f)
            if r is not None:
                last = r
        return last

    def _on_operator(self, event: UtteranceEvent) -> None:
        if self.bridge is not None:
            self.bridge.emit_speaker(True)
            self.bridge.on_agent_event(
                TrajectoryEvent("observation", f'Heard: "{event.text}"', {"similarity": round(event.similarity, 3)})
            )
        result = self.runtime.run(event.text) if self.auto_run else None
        self.history.append(VoiceCommand(text=event.text, similarity=event.similarity, result=result))

    def _on_event(self, event: UtteranceEvent) -> None:
        # Fires for every finalized utterance; act only on ignored non-operator speech.
        if not event.accepted and event.reason == "unrecognized_speaker":
            self.ignored_count += 1
            if self.bridge is not None:
                self.bridge.emit_speaker(False)

    def _on_speech_start(self) -> None:
        # Barge-in: the operator started speaking — signal listening (TTS should duck).
        if self.bridge is not None:
            self.bridge.emit_voice_active(True)
