import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_brief import build_reference_image_brief_update  # noqa: E402
from mission_control_server import ObserveServer  # noqa: E402


def test_reference_image_without_caption_marks_slots_pending_not_fake_filled():
    update = build_reference_image_brief_update({
        "image_name": "dragon-sketch.png",
        "image_type": "image/png",
        "image_bytes_b64": "c2tldGNo",
    })

    assert update["ok"] is True
    assert update["status"] == "awaiting_vision_caption"
    assert update["attachment"]["name"] == "dragon-sketch.png"
    assert update["attachment"]["source"] == "upload"
    assert set(update["slots"]) == {"cast", "style", "shot"}
    assert all(slot["state"] == "pending" for slot in update["slots"].values())
    assert all(slot["value"] == "" for slot in update["slots"].values())
    assert "awaiting vision caption" in update["message"].lower()


def test_reference_image_manual_constraints_update_slots_without_caption():
    update = build_reference_image_brief_update({
        "image_url": "data:image/png;base64,c2tldGNo",
        "constraints": {
            "cast": "one brass automaton",
            "style": "soft charcoal concept art",
            "shot": "wide low-angle hero shot",
        },
    })

    assert update["ok"] is True
    assert update["status"] == "manual_constraints_applied"
    assert update["slots"]["cast"] == {
        "state": "constrained",
        "value": "one brass automaton",
        "source": "manual",
    }
    assert update["slots"]["style"]["value"] == "soft charcoal concept art"
    assert update["slots"]["shot"]["value"] == "wide low-angle hero shot"


def test_reference_image_rejects_missing_image_payload():
    update = build_reference_image_brief_update({"constraints": {"cast": "dragon"}})

    assert update["ok"] is False
    assert update["status"] == "error"
    assert "image" in update["message"].lower()


def test_reference_image_endpoint_returns_pending_slots(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    server = ObserveServer(dist, port=0)
    server.start()
    assert server._httpd is not None
    port = server._httpd.server_address[1]
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/agent/brief/reference-image",
            data=json.dumps({"image_url": "data:image/png;base64,c2tldGNo"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    finally:
        server.stop()

    assert body["ok"] is True
    assert body["status"] == "awaiting_vision_caption"
    assert body["slots"]["cast"]["state"] == "pending"
