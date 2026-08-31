"""Deterministic stub backends for voice pipeline testing (no GPU/mic)."""

from __future__ import annotations

from typing import List

import numpy as np


class StubVAD:
    """Treat frames above a simple energy threshold as speech."""

    def __init__(self, threshold: float = 0.01):
        self.threshold = threshold

    def is_speech(self, frame: np.ndarray) -> bool:
        if frame.size == 0:
            return False
        energy = float(np.mean(np.abs(frame)))
        return energy >= self.threshold


class StubEmbedder:
    """Map audio to a fixed-dim vector from mean/std (deterministic per clip)."""

    def __init__(self, dim: int = 8):
        self.dim = dim

    def embed(self, audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return np.zeros(self.dim, dtype=np.float32)
        stats = [float(np.mean(audio)), float(np.std(audio)), float(np.max(audio)), float(np.min(audio))]
        vec = np.array(stats + [0.0] * max(0, self.dim - len(stats)), dtype=np.float32)[: self.dim]
        norm = np.linalg.norm(vec) or 1.0
        return vec / norm


class StubASR:
    """Return a fixed transcript when energy is present."""

    def __init__(self, text: str = "spawn a cube at the origin"):
        self.text = text

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        return self.text


def frames_from_wav(path: str, frame_size: int = 512) -> List[np.ndarray]:
    """Load a mono WAV as float32 frames (requires scipy only in test/dev)."""
    import wave

    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    if sample_width != 2:
        raise ValueError("only 16-bit PCM WAV supported in stub loader")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)
    return [data[i : i + frame_size] for i in range(0, len(data), frame_size) if data[i : i + frame_size].size]
