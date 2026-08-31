"""Tests for Prometheus metrics registry and server."""

import httpx

from hephaestus_forge.runtime.metrics import MetricsRegistry, MetricsServer


def test_registry_render_includes_counters():
    reg = MetricsRegistry()
    reg.record_tool("world.spawn_actor", True, 12.5)
    reg.record_tool("world.spawn_actor", False, 3.0, error_kind="command")
    reg.record_llm(45.0)
    text = reg.render()
    assert "hephaestus_tool_calls_total" in text
    assert "hephaestus_llm_latency_ms" in text
    assert 'tool="world.spawn_actor"' in text


def test_metrics_server_serves_metrics():
    reg = MetricsRegistry()
    reg.record_step()
    server = MetricsServer(host="127.0.0.1", port=0, registry=reg)
    # Bind to ephemeral port by patching after start - use fixed port with retry
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server.port = port
    server.start()
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=2.0)
        assert resp.status_code == 200
        assert "hephaestus_agent_loop_steps_total" in resp.text or "hephaestus_tool" in resp.text
    finally:
        server.stop()
