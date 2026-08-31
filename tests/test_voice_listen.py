"""Tests for stub voice backends and listen helper."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from hephaestus_forge.runtime.voice.backends import StubASR, StubEmbedder, StubVAD, frames_from_wav
from hephaestus_forge.runtime.voice.pipeline import RealtimeVoicePipeline
from hephaestus_forge.runtime.voice.speaker import SpeakerVerifier


def test_stub_vad_detects_energy():
    vad = StubVAD(threshold=0.01)
    assert vad.is_speech(np.full(128, 0.5)) is True
    assert vad.is_speech(np.zeros(128)) is False


def test_stub_embedder_returns_unit_vector():
    emb = StubEmbedder(dim=8)
    vec = emb.embed(np.full(256, 0.3))
    assert vec.shape == (8,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


def test_stub_asr_returns_text_for_non_empty():
    asr = StubASR(text="hello")
    assert asr.transcribe(np.zeros(0)) == ""
    assert asr.transcribe(np.full(64, 0.2)) == "hello"


def test_frames_from_wav_roundtrip(tmp_path: Path):
    path = tmp_path / "clip.wav"
    samples = (np.sin(np.linspace(0, 8, 2048)) * 16000).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(samples.tobytes())

    frames = frames_from_wav(str(path), frame_size=512)
    assert len(frames) >= 3
    assert all(f.dtype == np.float32 for f in frames)


def test_stub_pipeline_with_backends_accepts_operator():
    verifier = SpeakerVerifier(threshold=0.5)
    ref = StubEmbedder().embed(np.full(512, 0.5))
    verifier.enroll([ref], name="operator")

    accepted = []
    pipe = RealtimeVoicePipeline(
        StubVAD(threshold=0.01),
        StubEmbedder(),
        StubASR(text="build a tower"),
        verifier,
        min_speech_frames=3,
        hangover_frames=2,
        on_utterance=lambda e: accepted.append(e.text),
    )
    stream = [np.full(512, 0.5, dtype=np.float32) for _ in range(5)] + [np.zeros(512, dtype=np.float32) for _ in range(3)]
    for frame in stream:
        pipe.process_frame(frame)
    assert accepted == ["build a tower"]
