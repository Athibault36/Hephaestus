"""Observe / suite resilience: PIE drop and NIM timeout must not hard-crash."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ue_agent_loop import (  # noqa: E402
    AgentAction,
    ObserveActLoop,
    UePieOfflineError,
)


class _RefusedClient:
    def command(self, body):
        return {
            "success": False,
            "error": (
                "<urlopen error [WinError 10061] No connection could be made "
                "because the target machine actively refused it>"
            ),
            "result_json": "{}",
        }

    def frame(self):
        return b""

    def health(self):
        return {}


class _SoftFailClient:
    def command(self, body):
        cmd = body.get("command")
        if cmd == "vision.capture_frame":
            return {"success": False, "error": "HTTP 500: boom", "result_json": "{}"}
        if cmd == "world.list_actors":
            return {"success": True, "result_json": '{"actors":[],"actor_paths":[]}'}
        return {"success": False, "error": "x", "result_json": "{}"}

    def frame(self):
        return b""

    def health(self):
        return {}


def test_observe_raises_on_connection_refused():
    loop = ObserveActLoop(client=_RefusedClient(), require_nim=True)
    try:
        loop.observe()
        raise AssertionError("expected UePieOfflineError")
    except UePieOfflineError:
        pass


def test_observe_soft_fails_non_connection_capture_error():
    loop = ObserveActLoop(client=_SoftFailClient())
    snap = loop.observe()
    assert snap.frame_bytes == 0
    assert "error" in snap.frame_meta


def test_step_returns_on_llm_error_when_require_nim():
    class _OkClient(_SoftFailClient):
        def command(self, body):
            cmd = body.get("command")
            if cmd == "vision.capture_frame":
                return {"success": True, "result_json": '{"width":1,"height":1}'}
            return super().command(body)

        def frame(self):
            return b"PNG"

    def planner(_snap, _mem=None):
        return AgentAction(
            kind="llm_error",
            reason="DeepSeek planner failed: The read operation timed out",
            command={"command": "world.list_actors", "params": {}},
        )

    loop = ObserveActLoop(client=_OkClient(), require_nim=True, planner=planner)
    result = loop.step(1)
    assert result.ok is False
    assert result.action.kind == "llm_error"
    assert "timed out" in (result.act_result.get("error") or "")


def test_step_survives_pie_drop_mid_reobserve():
    class _DieOnSecondObserve:
        def __init__(self):
            self.captures = 0

        def command(self, body):
            cmd = body.get("command")
            if cmd == "vision.capture_frame":
                self.captures += 1
                if self.captures >= 2:
                    return {
                        "success": False,
                        "error": "[WinError 10061] refused",
                        "result_json": "{}",
                    }
                return {"success": True, "result_json": '{"width":1,"height":1}'}
            if cmd == "world.list_actors":
                return {"success": True, "result_json": '{"actors":[],"actor_paths":[]}'}
            if cmd == "spawn.static_mesh":
                return {"success": True, "result_json": "{}"}
            return {"success": True, "result_json": "{}"}

        def frame(self):
            return b"PNG"

        def health(self):
            return {}

    def planner(_snap, _mem=None):
        return AgentAction(
            kind="spawn_mesh",
            reason="spawn",
            command={"command": "spawn.static_mesh", "params": {}},
        )

    loop = ObserveActLoop(client=_DieOnSecondObserve(), require_nim=True, planner=planner)
    result = loop.step(1)
    assert result.ok is False
    assert "PIE offline" in (result.act_result.get("error") or "") or result.reobservation.frame_bytes == 0
