"""Mocked UE Remote API integration tests (no live PIE)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ue_agent_loop import ObserveActLoop, RemoteUeClient, WorldSnapshot  # noqa: E402
from ue_vision_planner import plan_dict_to_action  # noqa: E402


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_remote_client_retries_then_succeeds():
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("offline")
        return _FakeResponse(
            json.dumps({"success": True, "error": "", "result_json": "{}"}).encode("utf-8")
        )

    client = RemoteUeClient(retries=2, retry_delay=0)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.command({"command": "world.list_actors", "params": {}})
    assert result.get("success") is True
    assert calls["n"] == 2


def test_mock_observe_act_one_step():
    health = {"ok": True, "service": "hephaestus-remote", "plugin_version": "0.1.1"}
    capture = {
        "success": True,
        "result_json": json.dumps({"width": 640, "height": 360, "path": "/tmp/frame.png"}),
    }
    listed = {
        "success": True,
        "result_json": json.dumps({"actors": ["/Temp/PointLight_0"]}),
        "actor_paths": ["/Temp/PointLight_0"],
    }
    view = {
        "success": True,
        "result_json": json.dumps({
            "location": {"x": 0, "y": 0, "z": 200},
            "forward": {"x": 1, "y": 0, "z": 0},
        }),
    }
    pawn = {"success": True, "result_json": json.dumps({"speed": 0, "is_moving": False})}
    spawn_ok = {"success": True, "error": "", "result_json": "{}"}

    def fake_command(payload):
        cmd = payload.get("command")
        if cmd == "vision.capture_frame":
            return capture
        if cmd == "world.list_actors":
            return listed
        if cmd == "world.get_view":
            return view
        if cmd == "world.get_pawn_state":
            return pawn
        if cmd == "world.spawn_mesh":
            return spawn_ok
        return {"success": False, "error": f"unexpected {cmd}"}

    client = RemoteUeClient()
    client.health = lambda: health  # type: ignore[method-assign]
    client.command = fake_command  # type: ignore[method-assign]
    client.frame = lambda: b"\x89PNG\r\n"  # type: ignore[method-assign]

    loop = ObserveActLoop(client=client, seed=0, goal="seed cubes")
    results = loop.run(steps=1)
    assert len(results) == 1
    assert results[0].ok is True


def test_sequence_commands_validate_in_planner():
    snap = WorldSnapshot(actor_paths=[])
    cmd = plan_dict_to_action(
        {
            "action": "play_level_sequence",
            "sequence_path": "/Game/Cinematics/Shot01.Shot01",
            "reason": "cinematic",
        },
        snap,
    )
    assert cmd.command["command"] == "sequence.play"
