import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_chat import run_chat  # noqa: E402


def test_run_chat_offline_with_mock_ue(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if url.endswith("/v1/health"):
            payload = {"ok": True, "plugin_version": "0.1.1"}
        elif "/v1/command" in url:
            body = json.loads(req.data.decode("utf-8"))
            cmd = body.get("command")
            if cmd == "vision.capture_frame":
                payload = {"success": True, "result_json": json.dumps({"width": 64, "height": 64})}
            elif cmd == "world.list_actors":
                payload = {"success": True, "result_json": json.dumps({"actors": []}), "actor_paths": []}
            elif cmd == "world.get_view":
                payload = {"success": True, "result_json": json.dumps({"location": {"x": 0, "y": 0, "z": 200}, "forward": {"x": 1, "y": 0, "z": 0}})}
            elif cmd == "world.get_pawn_state":
                payload = {"success": True, "result_json": json.dumps({"speed": 0})}
            else:
                payload = {"success": True, "result_json": "{}"}
        else:
            payload = {}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    monkeypatch.setenv("HEPHAESTUS_ORCHESTRATOR", "default")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("ue_vision_planner.VisionLLMPlanner.available", False):
            out = run_chat("seed a lit scene with two cubes", project_root=tmp_path, max_steps=2)
    assert "reply" in out or "session" in out
