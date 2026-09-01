import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_chat import run_chat  # noqa: E402


def test_run_chat_direct_spawn(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agent_chat.spawn_asset_in_view",
        lambda client, path, **kw: [{"success": True, "result_json": "{}"}],
    )
    out = run_chat("/Game/Meshes/Cube.Cube", project_root=tmp_path, max_steps=1)
    assert out["planner"] == "direct_spawn"
    assert out["ok"] is True
