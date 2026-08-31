"""Operator enrollment: build and persist the voice profile Hephaestus obeys.

Enrollment takes several speaker embeddings of the operator (produced by a
speaker-embedding model from short audio clips) and builds a verified profile.
It also runs a consistency check — if the samples don't agree with each other
(noise, or a different person mixed in), enrollment is flagged so we don't
enroll a bad profile that would then accept the wrong voice.

The audio→embedding step needs a model (GPU-gated); this module operates on
embeddings so it is fully unit-testable, and a pluggable ``SpeakerEmbedder`` lets
the real audio path drop in later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import List, Optional

import numpy as np

from .speaker import DEFAULT_THRESHOLD, SpeakerVerifier, cosine_similarity

DEFAULT_PROFILE_REL = ".hephaestus_forge/voice/operator.json"
DEFAULT_MIN_CONSISTENCY = 0.6
MIN_RECOMMENDED_SAMPLES = 3


@dataclass
class EnrollmentResult:
    name: str
    num_samples: int
    consistency: float           # min pairwise cosine similarity among samples
    dim: int
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings


def pairwise_min_similarity(embeddings: List[np.ndarray]) -> float:
    """Lowest cosine similarity between any two enrollment samples (1.0 if <2)."""
    if len(embeddings) < 2:
        return 1.0
    return min(cosine_similarity(a, b) for a, b in combinations(embeddings, 2))


def enroll_from_embeddings(
    embeddings: List[np.ndarray],
    *,
    name: str = "operator",
    threshold: float = DEFAULT_THRESHOLD,
    min_consistency: float = DEFAULT_MIN_CONSISTENCY,
) -> tuple[SpeakerVerifier, EnrollmentResult]:
    """Build a SpeakerVerifier from embeddings, with a consistency check."""
    if not embeddings:
        raise ValueError("At least one embedding is required to enroll.")

    verifier = SpeakerVerifier(threshold=threshold)
    profile = verifier.enroll(embeddings, name=name)

    consistency = pairwise_min_similarity(embeddings)
    warnings: List[str] = []
    if len(embeddings) < MIN_RECOMMENDED_SAMPLES:
        warnings.append(
            f"Only {len(embeddings)} sample(s); {MIN_RECOMMENDED_SAMPLES}+ recommended for a robust profile."
        )
    if consistency < min_consistency:
        warnings.append(
            f"Enrollment samples are inconsistent (min pairwise similarity {consistency:.2f} < "
            f"{min_consistency:.2f}); they may include noise or more than one speaker."
        )

    result = EnrollmentResult(
        name=name, num_samples=profile.num_samples, consistency=consistency,
        dim=profile.dim, warnings=warnings,
    )
    return verifier, result


class EnrollmentStore:
    """Persists the operator profile under a project directory."""

    def __init__(self, project_root: Path, rel_path: str = DEFAULT_PROFILE_REL):
        self.path = Path(project_root) / rel_path

    def exists(self) -> bool:
        return self.path.exists()

    def save(self, verifier: SpeakerVerifier) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        verifier.save(self.path)
        return self.path

    def load(self, threshold: float = DEFAULT_THRESHOLD) -> Optional[SpeakerVerifier]:
        if not self.exists():
            return None
        verifier = SpeakerVerifier(threshold=threshold)
        verifier.load(self.path)
        return verifier
