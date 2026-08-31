"""Tests for shared observability bootstrap."""

from pathlib import Path

from hephaestus_forge.runtime.config import ObservabilityConfig
from hephaestus_forge.runtime.observability import start_observability


def test_start_observability_starts_metrics_server():
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    obs = ObservabilityConfig(metrics_enabled=True, metrics_port=port)
    runtime = start_observability(obs, Path("/tmp/project"))
    try:
        assert runtime.metrics_registry is not None
        assert runtime.metrics_server is not None
    finally:
        runtime.stop()


def test_start_observability_resolves_jsonl_path():
    obs = ObservabilityConfig(log_format="jsonl", log_dir="logs")
    runtime = start_observability(obs, Path("/tmp/project"))
    assert runtime.trajectory_log_path == Path("/tmp/project/logs/agent_trajectory.jsonl")
    runtime.stop()
