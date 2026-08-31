"""Tests for deploy lifecycle helpers."""

from hephaestus_forge.runtime.deploy_helpers import bridge_env_from_config, wait_for_url


def test_bridge_env_from_config_sets_port_and_token(monkeypatch):
    monkeypatch.setenv("HEPHAESTUS_BRIDGE_TOKEN", "env-secret")
    env = bridge_env_from_config({
        "network": {"ue_bridge_port": 9001},
        "security": {"require_auth": True, "localhost_only": True},
    })
    assert env["HEPHAESTUS_UE_PORT"] == "9001"
    assert env["HEPHAESTUS_BRIDGE_TOKEN"] == "env-secret"
    assert env["HEPHAESTUS_REQUIRE_AUTH"] == "1"
    assert env["HEPHAESTUS_LOCALHOST_ONLY"] == "1"


def test_wait_for_url_succeeds_when_getter_returns_true():
    calls = []

    def fast_ok(url, timeout):
        calls.append(url)
        return True, "ok"

    assert wait_for_url("http://test/health", timeout=1.0, interval=0.01, getter=fast_ok) is True
    assert calls


def test_wait_for_url_times_out():
    def never(url, timeout):
        return False, "down"

    assert wait_for_url("http://test/health", timeout=0.05, interval=0.01, getter=never) is False
