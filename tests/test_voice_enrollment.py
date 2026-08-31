from pathlib import Path

import numpy as np

from hephaestus_forge.runtime.voice import (
    EnrollmentStore,
    enroll_from_embeddings,
    pairwise_min_similarity,
)

OPERATOR = np.array([1.0, 0.0, 0.0, 0.0])
NEAR = np.array([0.97, 0.24, 0.0, 0.0])
FAR = np.array([0.0, 1.0, 0.0, 0.0])


def test_pairwise_min_similarity():
    assert pairwise_min_similarity([OPERATOR]) == 1.0
    assert pairwise_min_similarity([OPERATOR, OPERATOR]) == 1.0
    assert pairwise_min_similarity([OPERATOR, FAR]) == 0.0


def test_enroll_consistent_samples_ok():
    verifier, result = enroll_from_embeddings([OPERATOR, NEAR, OPERATOR], name="alex")
    assert result.name == "alex"
    assert result.num_samples == 3
    assert result.consistency > 0.9
    assert result.ok is True and not result.warnings
    assert verifier.verify(OPERATOR).accepted is True


def test_enroll_inconsistent_samples_warns():
    _, result = enroll_from_embeddings([OPERATOR, FAR, OPERATOR])
    assert result.consistency == 0.0
    assert any("inconsistent" in w for w in result.warnings)
    assert result.ok is False


def test_enroll_few_samples_warns():
    _, result = enroll_from_embeddings([OPERATOR])
    assert any("recommended" in w for w in result.warnings)


def test_enrollment_store_roundtrip(tmp_path: Path):
    store = EnrollmentStore(tmp_path)
    assert store.exists() is False
    verifier, _ = enroll_from_embeddings([OPERATOR, NEAR, OPERATOR], name="alex", threshold=0.8)
    saved = store.save(verifier)
    assert saved.exists() and store.exists()

    loaded = store.load(threshold=0.8)
    assert loaded is not None and loaded.is_enrolled
    assert loaded.profile.name == "alex"
    assert loaded.verify(OPERATOR).accepted is True
    assert loaded.verify(FAR).accepted is False
