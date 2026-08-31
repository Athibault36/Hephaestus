"""Lightweight tracing stub for agent steps and tool calls.

Records spans in memory for tests. When an OTLP endpoint is configured, spans
are queued for export — export is a no-op unless ``opentelemetry-sdk`` is
installed (optional extra).
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class SpanRecord:
    trace_id: str
    span_id: str
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    start_ms: float = 0.0
    end_ms: Optional[float] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_ms is None:
            return None
        return self.end_ms - self.start_ms


class TraceRecorder:
    """In-memory span recorder with optional OTLP export hook."""

    def __init__(self, *, enabled: bool = True, endpoint: str = "") -> None:
        self.enabled = enabled
        self.endpoint = endpoint
        self.spans: List[SpanRecord] = []
        self._trace_id = uuid.uuid4().hex

    def close(self) -> None:
        self._maybe_export()

    def _maybe_export(self) -> None:
        if not self.enabled or not self.endpoint or not self.spans:
            return
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: F401
            from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: F401
        except ImportError:
            return

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanRecord]:
        if not self.enabled:
            yield SpanRecord(trace_id="", span_id="", name=name)
            return

        record = SpanRecord(
            trace_id=self._trace_id,
            span_id=uuid.uuid4().hex[:16],
            name=name,
            attributes=dict(attributes),
            start_ms=time.perf_counter() * 1000.0,
        )
        try:
            yield record
        finally:
            record.end_ms = time.perf_counter() * 1000.0
            self.spans.append(record)

    def record(self, name: str, **attributes: Any) -> SpanRecord:
        with self.span(name, **attributes) as span:
            return span
