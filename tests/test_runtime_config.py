"""Tests for runtime config resolution."""

from pathlib import Path

from hephaestus_forge.runtime.config import (
    RuntimeConfig,
    find_project_config,
    load_observability_config,
    load_runtime_config,
)


SAMPLE = Path(__file__).resolve().parents[1] / "hephaestus_forge" / "forge_config" / "config.yaml"


def test_from_yaml_reads_ports_and_security(monkeypatch):
    monkeypatch.delenv("HEPHAESTUS_UE_URL", raising=False)
    cfg = RuntimeConfig.from_yaml(SAMPLE)
    assert cfg.ue_bridge_url == "http://127.0.0.1:8099"
    assert cfg.mission_bridge_port == 8081
    assert cfg.dashboard_port == 3000
    assert cfg.localhost_only is True
    assert cfg.require_auth is False


def test_env_overrides_ue_url(monkeypatch):
    monkeypatch.setenv("HEPHAESTUS_UE_URL", "http://10.0.0.5:9000")
    cfg = RuntimeConfig.from_yaml(SAMPLE)
    assert cfg.ue_bridge_url == "http://10.0.0.5:9000"


def test_bridge_token_from_env(monkeypatch):
    monkeypatch.setenv("HEPHAESTUS_BRIDGE_TOKEN", "secret")
    cfg = RuntimeConfig.from_yaml(SAMPLE)
    assert cfg.ue_bridge_token == "secret"
    assert cfg.auth_headers["X-Hephaestus-Token"] == "secret"


def test_find_project_config_falls_back_to_template():
    path = find_project_config(Path("/nonexistent"))
    assert path is not None
    assert path.name == "config.yaml"


def test_load_runtime_config_without_project():
    cfg = load_runtime_config(Path("/tmp/no-hephaestus-project"))
    assert "8099" in cfg.ue_bridge_url


def test_load_observability_config_from_template():
    obs = load_observability_config(Path(__file__).resolve().parents[1] / "hephaestus_forge")
    assert obs.log_format == "jsonl"
    assert obs.metrics_enabled is True
    assert obs.metrics_port == 9090
    assert obs.tracing_enabled is True
    assert "4318" in obs.tracing_endpoint
