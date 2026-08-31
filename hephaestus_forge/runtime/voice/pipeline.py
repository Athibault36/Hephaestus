"""Always-on voice pipeline: listen continuously, act only on the operator.

No push-to-talk. Audio frames stream in continuously; a VAD segments them into
utterances; each finished utterance is speaker-verified and ONLY the enrolled
operator's speech is transcribed and dispatched to the agent. Other speakers are
detected and ignored (and never transcribed — privacy + compute).

The VAD / speaker-embedding / ASR backends are injected via Protocols so real
models (silero-vad, ECAPA-TDNN or NVIDIA TitaNet, faster-whisper) plug in near
the GPU, while this gating state machine is fully unit tested with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Protocol

import numpy as np

from .speaker import SpeakerVerifier, VerificationResult


class VADBackend(Protocol):
    def is_speech(self, frame: np.ndarray) -> bool: ...


class SpeakerEmbedder(Protocol):
    def embed(self, audio: np.ndarray) -> np.ndarray: ...


class ASRBackend(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


@dataclass
class UtteranceEvent:
    """The outcome of one detected utterance."""

    accepted: bool          # True only if the enrolled operator spoke it
    similarity: float
    threshold: float
    num_frames: int
    text: str = ""          # transcribed ONLY when accepted
    speaker: Optional[str] = None
    reason: str = ""        # e.g. "operator", "unrecognized_speaker", "too_short"

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "similarity": round(self.similarity, 4),
            "threshold": self.threshold,
            "num_frames": self.num_frames,
            "text": self.text,
            "speaker": self.speaker,
            "reason": self.reason,
        }


class RealtimeVoicePipeline:
    """Continuous listen -> segment -> verify -> (operator only) transcribe.

    Args:
        vad: Voice-activity detector.
        embedder: Speaker-embedding backend.
        asr: Speech-to-text backend (only invoked for the operator's speech).
        verifier: Enrolled-operator verifier.
        min_speech_frames: Minimum speech frames for a segment to count (filters blips).
        hangover_frames: Consecutive silence frames that end an utterance.
        on_utterance: Called with accepted (operator) utterances only.
        on_event: Called with every finalized utterance (accepted or rejected).
        on_speech_start / on_speech_end: For TTS barge-in (duck output while the
            operator is speaking).
    """

    def __init__(
        self,
        vad: VADBackend,
        embedder: SpeakerEmbedder,
        asr: ASRBackend,
        verifier: SpeakerVerifier,
        *,
        min_speech_frames: int = 3,
        hangover_frames: int = 5,
        on_utterance: Optional[Callable[[UtteranceEvent], None]] = None,
        on_event: Optional[Callable[[UtteranceEvent], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        on_speech_end: Optional[Callable[[], None]] = None,
    ):
        self.vad = vad
        self.embedder = embedder
        self.asr = asr
        self.verifier = verifier
        self.min_speech_frames = max(1, int(min_speech_frames))
        self.hangover_frames = max(1, int(hangover_frames))
        self.on_utterance = on_utterance
        self.on_event = on_event
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

        self._in_speech = False
        self._buffer: List[np.ndarray] = []
        self._speech_frames = 0
        self._silence_run = 0

    @property
    def is_speaking(self) -> bool:
        """True while the operator (or anyone) is mid-utterance — used for barge-in."""
        return self._in_speech

    def process_frame(self, frame: np.ndarray) -> Optional[UtteranceEvent]:
        """Feed one audio frame. Returns an event when an utterance finalizes."""
        speech = bool(self.vad.is_speech(frame))

        if speech:
            if not self._in_speech:
                self._in_speech = True
                self._buffer = []
                self._speech_frames = 0
                self._silence_run = 0
                if self.on_speech_start:
                    self.on_speech_start()
            self._buffer.append(frame)
            self._speech_frames += 1
            self._silence_run = 0
            return None

        # silence
        if self._in_speech:
            self._silence_run += 1
            self._buffer.append(frame)
            if self._silence_run >= self.hangover_frames:
                return self._finalize()
        return None

    def flush(self) -> Optional[UtteranceEvent]:
        """Finalize any trailing utterance (e.g. on stream end)."""
        if self._in_speech:
            return self._finalize()
        return None

    def _finalize(self) -> Optional[UtteranceEvent]:
        buffer = self._buffer
        speech_frames = self._speech_frames
        self._in_speech = False
        self._buffer = []
        self._speech_frames = 0
        self._silence_run = 0
        if self.on_speech_end:
            self.on_speech_end()

        if speech_frames < self.min_speech_frames:
            event = UtteranceEvent(
                accepted=False, similarity=0.0, threshold=self.verifier.threshold,
                num_frames=speech_frames, reason="too_short",
            )
            self._emit(event)
            return event

        audio = np.concatenate([np.asarray(f).reshape(-1) for f in buffer]) if buffer else np.array([])
        embedding = self.embedder.embed(audio)
        result: VerificationResult = self.verifier.verify(embedding)

        if result.accepted:
            text = self.asr.transcribe(audio)  # transcribe operator speech only
            event = UtteranceEvent(
                accepted=True, similarity=result.similarity, threshold=result.threshold,
                num_frames=speech_frames, text=text, speaker=result.speaker, reason="operator",
            )
        else:
            # Do NOT transcribe non-operator speech.
            event = UtteranceEvent(
                accepted=False, similarity=result.similarity, threshold=result.threshold,
                num_frames=speech_frames, reason="unrecognized_speaker",
            )

        self._emit(event)
        return event

    def _emit(self, event: UtteranceEvent) -> None:
        if self.on_event:
            self.on_event(event)
        if event.accepted and self.on_utterance:
            self.on_utterance(event)
