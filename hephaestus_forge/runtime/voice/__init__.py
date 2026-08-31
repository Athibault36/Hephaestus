"""Real-time, speaker-verified voice for Hephaestus.

Hephaestus listens continuously (no push-to-talk) and acts ONLY on speech that
matches the enrolled operator's voice:

- ``speaker``   enroll the operator and verify utterances by voice embedding.
- ``pipeline``  the always-on VAD -> speaker-verify -> STT gate, with pluggable
                VAD / speaker-embedding / ASR backends so heavy models
                (silero-vad, ECAPA/TitaNet, faster-whisper) drop in near the GPU
                while the gating logic stays unit-testable everywhere.
"""

from .speaker import SpeakerProfile, SpeakerVerifier, VerificationResult, cosine_similarity
from .pipeline import (
    ASRBackend,
    RealtimeVoicePipeline,
    SpeakerEmbedder,
    UtteranceEvent,
    VADBackend,
)
from .enrollment import (
    EnrollmentResult,
    EnrollmentStore,
    enroll_from_embeddings,
    pairwise_min_similarity,
)
from .session import VoiceAgentSession, VoiceCommand

__all__ = [
    "SpeakerProfile",
    "SpeakerVerifier",
    "VerificationResult",
    "cosine_similarity",
    "ASRBackend",
    "SpeakerEmbedder",
    "VADBackend",
    "RealtimeVoicePipeline",
    "UtteranceEvent",
    "EnrollmentResult",
    "EnrollmentStore",
    "enroll_from_embeddings",
    "pairwise_min_similarity",
    "VoiceAgentSession",
    "VoiceCommand",
]
