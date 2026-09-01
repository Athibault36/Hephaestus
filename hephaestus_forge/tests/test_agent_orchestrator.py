import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_orchestrator import run_agent  # noqa: E402


def test_run_agent_default_delegates_to_chat(monkeypatch, tmp_path):
    with patch("agent_chat.run_chat") as mock_chat:
        mock_chat.return_value = {"ok": True, "reply": "hi"}
        out = run_agent("hello", project_root=tmp_path)
        assert out["ok"] is True
        mock_chat.assert_called_once()


def test_run_agent_langgraph_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("HEPHAESTUS_ORCHESTRATOR", "langgraph")
    with patch("langgraph_runner.run_langgraph_goal", return_value={"ok": True, "planner": "langgraph-phased"}) as mock_lg:
        out = run_agent("spawn a dog", project_root=tmp_path)
        assert out["planner"] == "langgraph-phased"
        mock_lg.assert_called_once()
