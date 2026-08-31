"""Shared observability bootstrap for deploy and agent commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from .config import ObservabilityConfig, default_trajectory_log_path

if TYPE_CHECKING:
    from .metrics import MetricsRegistry, MetricsServer
    from .tracing import TraceRecorder


@dataclass
class ObservabilityRuntime:
    """Handles started by :func:`start_observability`; call :meth:`stop` on shutdown."""

    metrics_server: Optional["MetricsServer"] = None
    metrics_registry: Optional["MetricsRegistry"] = None
    tracer: Optional["TraceRecorder"] = None
    trajectory_log_path: Path | None = None

    @property
    def metrics_url(self) -> str | None:
        if self.metrics_server is None:
            return None
        return f"http://{self.metrics_server.host}:{self.metrics_server.port}/metrics"

    def stop(self) -> None:
        if self.metrics_server is not None:
            self.metrics_server.stop()
            self.metrics_server = None
        if self.tracer is not None:
            self.tracer.close()
            self.tracer = None


def start_observability(
    obs_cfg: ObservabilityConfig,
    project_root: Path,
    *,
    goal: str | None = None,
    log: Callable[[str], None] | None = None,
) -> ObservabilityRuntime:
    """Start metrics and tracing from config; optionally resolve JSONL log path."""
    runtime = ObservabilityRuntime()

    if obs_cfg.metrics_enabled:
        from .metrics import MetricsServer, get_metrics_registry

        runtime.metrics_registry = get_metrics_registry()
        runtime.metrics_server = MetricsServer(
            host=obs_cfg.metrics_host,
            port=obs_cfg.metrics_port,
            registry=runtime.metrics_registry,
        ).start()
        if log and runtime.metrics_url:
            log(f"Metrics at {runtime.metrics_url}")

    if obs_cfg.tracing_enabled:
        from .tracing import TraceRecorder

        runtime.tracer = TraceRecorder(
            enabled=True,
            endpoint=obs_cfg.tracing_endpoint,
        )

    if obs_cfg.log_format.lower() == "jsonl":
        runtime.trajectory_log_path = default_trajectory_log_path(project_root, obs_cfg)
        if log and goal is None:
            log(f"Trajectory log path: {runtime.trajectory_log_path}")

    return runtime
