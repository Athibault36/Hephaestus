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


def test_run_chat_direct_locomotion(monkeypatch, tmp_path):
    actor = "/Temp/UEDPIE_0.PersistentLevel.SkeletalMeshActor_0"
    client = type("C", (), {"command": lambda self, p: {"success": True, "result_json": "{}"}})()
    monkeypatch.setattr("agent_chat.RemoteUeClient", lambda *a, **k: client)
    out = run_chat(f"play idle animation on {actor}", project_root=tmp_path, max_steps=1)
    assert out["planner"] == "direct_locomotion"
    assert out["ok"] is True


def test_run_chat_direct_audio(monkeypatch, tmp_path):
    client = type("C", (), {"command": lambda self, p: {"success": True, "result_json": "{\"played\":true}"}})()
    monkeypatch.setattr("agent_chat.RemoteUeClient", lambda *a, **k: client)
    out = run_chat("play test audio", project_root=tmp_path, max_steps=1)
    assert out["planner"] == "direct_audio"
    assert out["ok"] is True


def test_run_chat_direct_search(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agent_chat.search_project_assets",
        lambda client, query, **kw: ["/Game/Meshes/Dog.Dog"],
    )
    client = type("C", (), {"command": lambda self, p: {"success": True}})()
    monkeypatch.setattr("agent_chat.RemoteUeClient", lambda *a, **k: client)
    out = run_chat("search assets for dog", project_root=tmp_path, max_steps=1)
    assert out["planner"] == "direct_search"
    assert "/Game/Meshes/Dog.Dog" in out["asset_matches"]
