"""Tests for deploy helpers and process supervisor."""

from __future__ import annotations

import subprocess
import sys
import time

from hephaestus_forge.runtime.deploy_helpers import (
    ProcessSupervisor,
    bridge_env_from_config,
    wait_for_url,
)


def test_bridge_env_from_config_includes_token_and_port():
    cfg = {
        "network": {"ue_bridge_port": 8199},
        "security": {"bridge_token": "abc", "require_auth": True, "localhost_only": False},
    }
    env = bridge_env_from_config(cfg)
    assert env["HEPHAESTUS_UE_PORT"] == "8199"
    assert env["HEPHAESTUS_BRIDGE_TOKEN"] == "abc"
    assert env["HEPHAESTUS_REQUIRE_AUTH"] == "1"
    assert "HEPHAESTUS_LOCALHOST_ONLY" not in env


def test_wait_for_url_times_out_on_unreachable():
    assert wait_for_url("http://127.0.0.1:1/nope", timeout=0.2, interval=0.05) is False


def test_process_supervisor_tracks_and_shuts_down():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with ProcessSupervisor(shutdown_timeout=2.0) as sup:
        sup.add("sleepy", proc)
        time.sleep(0.05)
        assert proc.poll() is None
    assert proc.poll() is not None
