"""In-memory Prometheus-style metrics for the agent runtime."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple


@dataclass
class _Counter:
    name: str
    help: str
    values: Dict[Tuple[Tuple[str, str], ...], float] = field(default_factory=dict)

    def inc(self, labels: Dict[str, str], amount: float = 1.0) -> None:
        key = tuple(sorted(labels.items()))
        self.values[key] = self.values.get(key, 0.0) + amount

    def render(self) -> List[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for key, val in sorted(self.values.items()):
            label_str = _format_labels(dict(key))
            lines.append(f"{self.name}{label_str} {val}")
        return lines


@dataclass
class _Histogram:
    name: str
    help: str
    buckets: Tuple[float, ...] = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf"))
    sums: Dict[Tuple[Tuple[str, str], ...], float] = field(default_factory=dict)
    counts: Dict[Tuple[Tuple[str, str], ...], int] = field(default_factory=dict)
    bucket_counts: Dict[Tuple[Tuple[str, str], ...], List[int]] = field(default_factory=dict)

    def observe(self, labels: Dict[str, str], value: float) -> None:
        key = tuple(sorted(labels.items()))
        self.sums[key] = self.sums.get(key, 0.0) + value
        self.counts[key] = self.counts.get(key, 0) + 1
        buckets = self.bucket_counts.setdefault(key, [0] * len(self.buckets))
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                buckets[i] += 1

    def render(self) -> List[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key in sorted(self.sums.keys()):
            labels = dict(key)
            label_str = _format_labels(labels)
            base = self.name + label_str
            buckets = self.bucket_counts.get(key, [0] * len(self.buckets))
            for bound, count in zip(self.buckets, buckets):
                le = "+Inf" if bound == float("inf") else str(bound)
                extra = dict(labels)
                extra["le"] = le
                lines.append(f'{self.name}_bucket{_format_labels(extra)} {count}')
            lines.append(f"{base}_sum {self.sums[key]}")
            lines.append(f"{base}_count {self.counts[key]}")
        return lines


def _format_labels(labels: Dict[str, str]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


@dataclass
class _LatencySamples:
    """Ring buffer for percentile estimates alongside Prometheus histograms."""

    max_samples: int = 2048
    values: List[float] = field(default_factory=list)

    def observe(self, value: float) -> None:
        self.values.append(value)
        if len(self.values) > self.max_samples:
            self.values = self.values[-self.max_samples :]

    def percentile(self, p: float) -> Optional[float]:
        if not self.values:
            return None
        ordered = sorted(self.values)
        idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
        return ordered[idx]


class MetricsRegistry:
    """Thread-safe metrics registry with Prometheus text exposition."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.agent_loop_steps = _Counter("hephaestus_agent_loop_steps_total", "Agent think/act iterations")
        self.tool_calls = _Counter("hephaestus_tool_calls_total", "Tool invocations")
        self.ue_errors = _Counter("hephaestus_ue_errors_total", "UE bridge errors by kind")
        self.tool_latency = _Histogram("hephaestus_tool_latency_ms", "Tool execution latency in ms")
        self.llm_latency = _Histogram("hephaestus_llm_latency_ms", "LLM chat latency in ms")
        self._tool_samples = _LatencySamples()
        self._llm_samples = _LatencySamples()

    def record_step(self) -> None:
        with self._lock:
            self.agent_loop_steps.inc({})

    def record_tool(self, tool: str, success: bool, latency_ms: float, error_kind: Optional[str] = None) -> None:
        status = "ok" if success else "error"
        with self._lock:
            self.tool_calls.inc({"tool": tool, "status": status})
            self.tool_latency.observe({"tool": tool}, latency_ms)
            self._tool_samples.observe(latency_ms)
            if not success and error_kind:
                self.ue_errors.inc({"kind": error_kind})

    def record_llm(self, latency_ms: float) -> None:
        with self._lock:
            self.llm_latency.observe({}, latency_ms)
            self._llm_samples.observe(latency_ms)

    def latency_summary(self) -> Dict[str, Optional[float]]:
        """Estimated p50/p95/p99 latencies in ms for tool and LLM paths."""
        with self._lock:
            return {
                "tool_p50_ms": self._tool_samples.percentile(50),
                "tool_p95_ms": self._tool_samples.percentile(95),
                "tool_p99_ms": self._tool_samples.percentile(99),
                "llm_p50_ms": self._llm_samples.percentile(50),
                "llm_p95_ms": self._llm_samples.percentile(95),
                "llm_p99_ms": self._llm_samples.percentile(99),
            }

    def render(self) -> str:
        with self._lock:
            parts: List[str] = []
            for block in (
                self.agent_loop_steps,
                self.tool_calls,
                self.ue_errors,
                self.tool_latency,
                self.llm_latency,
            ):
                parts.extend(block.render())
                parts.append("")
            return "\n".join(parts).strip() + "\n"


_GLOBAL: Optional[MetricsRegistry] = None


def get_metrics_registry() -> MetricsRegistry:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = MetricsRegistry()
    return _GLOBAL


class _MetricsHandler(BaseHTTPRequestHandler):
    registry: MetricsRegistry = get_metrics_registry()

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/metrics", "/"):
            self.send_response(404)
            self.end_headers()
            return
        body = self.registry.render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return  # quiet


class MetricsServer:
    """Background HTTP server exposing Prometheus metrics."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9090, registry: Optional[MetricsRegistry] = None):
        self.host = host
        self.port = port
        self.registry = registry or get_metrics_registry()
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "MetricsServer":
        handler = type("BoundMetricsHandler", (_MetricsHandler,), {"registry": self.registry})
        self._httpd = HTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
