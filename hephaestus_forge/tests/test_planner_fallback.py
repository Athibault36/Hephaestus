"""Planner retries DeepSeek once, then falls back to Lightning on timeout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ue_agent_loop import WorldSnapshot  # noqa: E402
from ue_vision_planner import VisionLLMPlanner  # noqa: E402


def test_chat_completion_falls_back_after_timeout(monkeypatch):
    calls: list[str] = []

    def fake_post(self, payload):  # noqa: ANN001
        calls.append(str(payload["model"]))
        if str(payload["model"]).startswith("deepseek"):
            raise TimeoutError("The read operation timed out")
        return {
            "choices": [
                {"message": {"content": '{"action":"noop","reason":"ok"}'}}
            ]
        }

    monkeypatch.setattr(VisionLLMPlanner, "_post_chat", fake_post)
    planner = VisionLLMPlanner(api_key="x", model="deepseek-ai/deepseek-v4-pro-0813")
    out = planner._ask(WorldSnapshot(), [])
    assert out["action"] == "noop"
    assert calls.count("deepseek-ai/deepseek-v4-pro-0813") == 2  # primary + retry
    assert any(c.startswith("nvidia/nemotron-3.5-lightning") for c in calls)
    assert "falling back" in (planner.last_error or "")
