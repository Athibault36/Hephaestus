import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_session import SessionStore  # noqa: E402


def test_session_reset_and_save(tmp_path):
    store = SessionStore(project_root=tmp_path)
    s = store.reset(goal="spawn cubes", mode="cinematic")
    assert s.goal == "spawn cubes"
    assert s.mode == "cinematic"
    s.add_assistant("working on it")
    store.save(s)
    loaded = store._load_latest()
    assert loaded is not None
    assert loaded.goal == "spawn cubes"
    assert any(m.role == "assistant" for m in loaded.messages)


def test_session_export_bundle(tmp_path):
    store = SessionStore(project_root=tmp_path)
    s = store.reset(goal="frame shot", mode="cinematic")
    bundle = s.export_bundle(thoughts=[{"kind": "plan", "content": "test"}])
    assert bundle["session"]["goal"] == "frame shot"
    assert bundle["schema_version"] == 4
    assert bundle["operator_milestone"] == "v1.0"
    assert bundle["thoughts"][0]["content"] == "test"
    assert "command_transcript" in bundle
