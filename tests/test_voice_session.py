"""VoiceAgentSession: recognized speech -> agent goal; other speakers ignored."""

from __future__ import annotations

from typing import List

import numpy as np

from hephaestus_forge.runtime.voice import RealtimeVoicePipeline, SpeakerVerifier, VoiceAgentSession

OPERATOR = np.array([1.0, 0.0, 0.0, 0.0])
IMPOSTOR = np.array([0.0, 1.0, 0.0, 0.0])


class FakeVAD:
    def is_speech(self, frame):
        return bool(np.any(np.asarray(frame) != 0))


class FakeEmbedder:
    def embed(self, audio):
        audio = np.asarray(audio).reshape(-1)
        nz = audio[audio != 0]
        tag = round(float(nz.mean())) if nz.size else 0
        return OPERATOR if tag == 1 else IMPOSTOR if tag == 2 else np.zeros(4)


class FakeASR:
    def transcribe(self, audio):
        return "spawn a cube"


class FakeRuntime:
    def __init__(self):
        self.goals: List[str] = []

    def run(self, goal):
        self.goals.append(goal)
        return {"goal": goal, "completed": True}


class FakeBridge:
    def __init__(self):
        self.speaker_events = []
        self.agent_events = []

    def emit_speaker(self, recognized):
        self.speaker_events.append(recognized)

    def emit_voice_active(self, active):
        pass

    def on_agent_event(self, event):
        self.agent_events.append(event)


def build(auto_run=True):
    verifier = SpeakerVerifier(threshold=0.75)
    verifier.enroll([OPERATOR])
    pipe = RealtimeVoicePipeline(FakeVAD(), FakeEmbedder(), FakeASR(), verifier,
                                 min_speech_frames=3, hangover_frames=2)
    runtime = FakeRuntime()
    bridge = FakeBridge()
    session = VoiceAgentSession(pipe, runtime, bridge=bridge, auto_run=auto_run)
    return session, runtime, bridge


def speech(value, n):
    return [np.full(8, value) for _ in range(n)]


def silence(n):
    return [np.zeros(8) for _ in range(n)]


def test_operator_command_runs_agent_and_reports_recognized():
    session, runtime, bridge = build()
    session.feed(speech(1.0, 4) + silence(2))
    assert runtime.goals == ["spawn a cube"]          # agent ran with the transcript
    assert session.history[-1].text == "spawn a cube"
    assert True in bridge.speaker_events              # reported recognized
    assert any(e.type == "observation" and "Heard" in e.content for e in bridge.agent_events)


def test_unrecognized_speaker_does_not_run_agent():
    session, runtime, bridge = build()
    session.feed(speech(2.0, 4) + silence(2))
    assert runtime.goals == []                         # agent NOT run
    assert session.ignored_count == 1
    assert bridge.speaker_events[-1] is False          # reported ignored


def test_mixed_stream_runs_agent_only_for_operator():
    session, runtime, bridge = build()
    session.feed(
        speech(1.0, 4) + silence(3)     # operator
        + speech(2.0, 4) + silence(3)   # impostor (ignored)
        + speech(1.0, 5) + silence(3)   # operator
    )
    assert runtime.goals == ["spawn a cube", "spawn a cube"]
    assert session.ignored_count == 1


def test_auto_run_false_records_without_running():
    session, runtime, bridge = build(auto_run=False)
    session.feed(speech(1.0, 4) + silence(2))
    assert runtime.goals == []
    assert len(session.history) == 1 and session.history[0].result is None
