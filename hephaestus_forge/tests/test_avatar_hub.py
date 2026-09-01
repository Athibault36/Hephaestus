import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from avatar_hub import AvatarHub, pick_form  # noqa: E402


def test_pick_form_from_state():
    assert pick_form("thinking") == 2
    assert pick_form("working") == 0


def test_pick_form_from_trigger():
    assert pick_form("idle", "acting") == 0
    assert pick_form("idle", "result_error") == 3


def test_hub_broadcast_updates_form():
    hub = AvatarHub()
    hub.broadcast(state="working", trigger="loop_start")
    assert hub.state == "working"
    assert 0 <= hub.form <= 3
