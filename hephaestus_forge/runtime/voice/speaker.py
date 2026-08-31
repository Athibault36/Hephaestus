"""Speaker verification: enroll the operator and accept only their voice.

Backend-agnostic — works on speaker embeddings (unit-agnostic float vectors)
produced by any model (ECAPA-TDNN, NVIDIA TitaNet, Resemblyzer, ...). The
verification math (L2-normalized cosine similarity vs. an enrolled centroid with
a decision threshold) is pure and unit tested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

DEFAULT_THRESHOLD = 0.75


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return vec / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors in [-1, 1]."""
    a = _l2_normalize(a)
    b = _l2_normalize(b)
    if a.shape != b.shape or a.size == 0:
        return 0.0
    return float(np.dot(a, b))


@dataclass
class SpeakerProfile:
    """An enrolled speaker: the mean (centroid) of their sample embeddings."""

    name: str
    centroid: np.ndarray
    num_samples: int = 0
    dim: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "centroid": np.asarray(self.centroid, dtype=np.float64).reshape(-1).tolist(),
            "num_samples": self.num_samples,
            "dim": self.dim,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpeakerProfile":
        centroid = _l2_normalize(np.asarray(data.get("centroid", []), dtype=np.float64))
        return cls(
            name=data.get("name", "operator"),
            centroid=centroid,
            num_samples=int(data.get("num_samples", 0)),
            dim=int(data.get("dim", centroid.size)),
        )


@dataclass
class VerificationResult:
    accepted: bool
    similarity: float
    threshold: float
    speaker: Optional[str] = None


class SpeakerVerifier:
    """Enroll the operator's voice and verify whether an utterance is theirs.

    Args:
        threshold: Minimum cosine similarity to accept an utterance as the
            enrolled operator. Higher = stricter (fewer false accepts).
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = float(threshold)
        self._profile: Optional[SpeakerProfile] = None
        self._samples: List[np.ndarray] = []

    @property
    def is_enrolled(self) -> bool:
        return self._profile is not None and self._profile.num_samples > 0

    @property
    def profile(self) -> Optional[SpeakerProfile]:
        return self._profile

    def enroll(self, embeddings: List[np.ndarray], name: str = "operator") -> SpeakerProfile:
        """Enroll (or replace) the operator from one or more voice embeddings."""
        if not embeddings:
            raise ValueError("At least one embedding is required to enroll a speaker.")
        self._samples = [_l2_normalize(e) for e in embeddings]
        return self._rebuild(name)

    def add_sample(self, embedding: np.ndarray, name: Optional[str] = None) -> SpeakerProfile:
        """Add another enrollment sample (adaptive enrollment)."""
        self._samples.append(_l2_normalize(embedding))
        return self._rebuild(name or (self._profile.name if self._profile else "operator"))

    def _rebuild(self, name: str) -> SpeakerProfile:
        stacked = np.vstack(self._samples)
        centroid = _l2_normalize(stacked.mean(axis=0))
        self._profile = SpeakerProfile(
            name=name, centroid=centroid, num_samples=len(self._samples), dim=centroid.size
        )
        return self._profile

    def verify(self, embedding: np.ndarray) -> VerificationResult:
        """Decide whether ``embedding`` is the enrolled operator."""
        if not self.is_enrolled:
            # Fail closed: with no enrollment, nothing is accepted as the operator.
            return VerificationResult(accepted=False, similarity=0.0, threshold=self.threshold)
        assert self._profile is not None
        sim = cosine_similarity(embedding, self._profile.centroid)
        return VerificationResult(
            accepted=sim >= self.threshold,
            similarity=sim,
            threshold=self.threshold,
            speaker=self._profile.name if sim >= self.threshold else None,
        )

    # -- persistence ---------------------------------------------------------
    def save(self, path: Path) -> None:
        if not self.is_enrolled:
            raise ValueError("Cannot save: no speaker enrolled.")
        assert self._profile is not None
        Path(path).write_text(json.dumps(self._profile.to_dict(), indent=2), encoding="utf-8")

    def load(self, path: Path) -> SpeakerProfile:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._profile = SpeakerProfile.from_dict(data)
        self._samples = [self._profile.centroid] if self._profile.num_samples else []
        return self._profile
