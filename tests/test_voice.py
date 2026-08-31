from pathlib import Path

import numpy as np

from hephaestus_forge.runtime.voice import (
    RealtimeVoicePipeline,
    SpeakerVerifier,
    UtteranceEvent,
    cosine_similarity,
)

OPERATOR = np.array([1.0, 0.0, 0.0, 0.0])
IMPOSTOR = np.array([0.0, 1.0, 0.0, 0.0])
NEARBY = np.array([0.96, 0.28, 0.0, 0.0])  # close to operator direction


# --- Speaker verification ---------------------------------------------------
def test_cosine_similarity_basic():
    assert cosine_similarity(OPERATOR, OPERATOR) == 1.0
    assert cosine_similarity(OPERATOR, IMPOSTOR) == 0.0


def test_enrolled_operator_accepted_impostor_rejected():
    v = SpeakerVerifier(threshold=0.75)
    v.enroll([OPERATOR, OPERATOR * 0.9], name="alex")
    assert v.is_enrolled

    ok = v.verify(OPERATOR)
    assert ok.accepted is True and ok.speaker == "alex" and ok.similarity > 0.75

    bad = v.verify(IMPOSTOR)
    assert bad.accepted is False and bad.speaker is None


def test_threshold_boundary():
    v = SpeakerVerifier(threshold=0.99)
    v.enroll([OPERATOR])
    # NEARBY is ~0.96 similar — below a very strict 0.99 threshold.
    assert v.verify(NEARBY).accepted is False
    v_loose = SpeakerVerifier(threshold=0.90)
    v_loose.enroll([OPERATOR])
    assert v_loose.verify(NEARBY).accepted is True


def test_fail_closed_when_not_enrolled():
    v = SpeakerVerifier()
    assert v.is_enrolled is False
    assert v.verify(OPERATOR).accepted is False  # nothing accepted without enrollment


def test_profile_save_load_roundtrip(tmp_path: Path):
    v = SpeakerVerifier(threshold=0.8)
    v.enroll([OPERATOR, OPERATOR], name="alex")
    p = tmp_path / "profile.json"
    v.save(p)

    v2 = SpeakerVerifier(threshold=0.8)
    prof = v2.load(p)
    assert prof.name == "alex"
    assert v2.verify(OPERATOR).accepted is True


# --- Pipeline (always-on, no push-to-talk) ----------------------------------
class FakeVAD:
    def is_speech(self, frame: np.ndarray) -> bool:
        return bool(np.any(np.asarray(frame) != 0))


class FakeEmbedder:
    """Maps a frame's speech value to a speaker embedding (1->operator, 2->impostor)."""

    def embed(self, audio: np.ndarray) -> np.ndarray:
        audio = np.asarray(audio).reshape(-1)
        nz = audio[audio != 0]
        tag = round(float(nz.mean())) if nz.size else 0
        if tag == 1:
            return OPERATOR
        if tag == 2:
            return IMPOSTOR
        return np.zeros(4)


class FakeASR:
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio: np.ndarray) -> str:
        self.calls += 1
        return "hello hephaestus"


def make_pipeline(**kwargs):
    v = SpeakerVerifier(threshold=0.75)
    v.enroll([OPERATOR])
    asr = FakeASR()
    accepted: list[UtteranceEvent] = []
    events: list[UtteranceEvent] = []
    pipe = RealtimeVoicePipeline(
        FakeVAD(), FakeEmbedder(), asr, v,
        min_speech_frames=3, hangover_frames=2,
        on_utterance=accepted.append, on_event=events.append,
        **kwargs,
    )
    return pipe, asr, accepted, events


def speech(value: float, n: int):
    return [np.full(8, value) for _ in range(n)]


def silence(n: int):
    return [np.zeros(8) for _ in range(n)]


def test_operator_utterance_is_transcribed_and_dispatched():
    pipe, asr, accepted, events = make_pipeline()
    result = None
    for f in speech(1.0, 4) + silence(2):
        r = pipe.process_frame(f)
        if r:
            result = r
    assert result is not None and result.accepted is True
    assert result.text == "hello hephaestus" and result.reason == "operator"
    assert asr.calls == 1
    assert len(accepted) == 1


def test_unrecognized_speaker_ignored_and_not_transcribed():
    pipe, asr, accepted, events = make_pipeline()
    for f in speech(2.0, 4) + silence(2):
        pipe.process_frame(f)
    assert len(accepted) == 0                 # not dispatched to the agent
    assert asr.calls == 0                      # never transcribed (privacy + compute)
    assert events and events[-1].reason == "unrecognized_speaker"


def test_short_blip_filtered():
    pipe, asr, accepted, events = make_pipeline()
    for f in speech(1.0, 1) + silence(2):
        pipe.process_frame(f)
    assert events and events[-1].reason == "too_short"
    assert len(accepted) == 0


def test_continuous_stream_only_operator_dispatched():
    pipe, asr, accepted, events = make_pipeline()
    stream = (
        speech(1.0, 4) + silence(3)   # operator
        + speech(2.0, 4) + silence(3)  # impostor
        + speech(1.0, 5) + silence(3)  # operator again
    )
    for f in stream:
        pipe.process_frame(f)
    assert len(accepted) == 2                  # both operator utterances
    assert all(e.accepted for e in accepted)
    assert asr.calls == 2                      # only operator speech transcribed
    reasons = [e.reason for e in events]
    assert reasons.count("operator") == 2 and reasons.count("unrecognized_speaker") == 1


def test_barge_in_speech_callbacks():
    starts = {"n": 0}
    ends = {"n": 0}
    pipe, asr, accepted, events = make_pipeline(
        on_speech_start=lambda: starts.__setitem__("n", starts["n"] + 1),
        on_speech_end=lambda: ends.__setitem__("n", ends["n"] + 1),
    )
    assert pipe.is_speaking is False
    pipe.process_frame(np.full(8, 1.0))
    assert pipe.is_speaking is True and starts["n"] == 1
    for f in speech(1.0, 3) + silence(2):
        pipe.process_frame(f)
    assert ends["n"] == 1 and pipe.is_speaking is False
