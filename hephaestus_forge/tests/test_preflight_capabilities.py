import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preflight_health import _probe_bridge_capabilities  # noqa: E402


def test_probe_bridge_capabilities_ok():
    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        cmd = body.get("command")
        if cmd == "animation.play_locomotion":
            payload = {"success": False, "error": "actor_path required"}
        elif cmd == "animation.play_montage":
            payload = {"success": False, "error": "actor_path required"}
        else:
            payload = {"success": True, "result_json": "{}"}
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        check = _probe_bridge_capabilities("http://127.0.0.1:8765")
    assert check.ok is True
    assert "Locomotion" in check.detail
