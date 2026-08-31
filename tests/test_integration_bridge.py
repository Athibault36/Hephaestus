"""Integration-style tests: full agent loop against fake UE with extended tools + auth."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hephaestus_forge.runtime.llm import LLMResponse, ToolCall
from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


class ScriptedLLM:
    def __init__(self, script: List[LLMResponse]):
        self.script = script
        self.calls = 0

    def chat(self, messages, tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        idx = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return self.script[idx]


def test_extended_tool_loop_with_auth():
    fake = FakeUE(require_auth=True, auth_token="integration")
    ue = UEClient(
        base_url="http://ue.test",
        transport=make_transport(fake),
        auth_token="integration",
    )
    registry = build_default_registry()

    script = [
        LLMResponse(
            content="Compile blueprint.",
            tool_calls=[
                ToolCall(
                    id="t1",
                    name="blueprint__compile",
                    arguments={"blueprint_path": "/Game/BP/BP_Hero.BP_Hero"},
                )
            ],
        ),
        LLMResponse(content="Blueprint compile requested."),
    ]
    runtime = AgentRuntime(ScriptedLLM(script), ue, registry, max_steps=4)
    result = runtime.run("Compile the hero blueprint")

    assert result.completed is True
    assert result.tool_calls == 1
    assert fake.received[-1]["command"] == "blueprint.compile"
    ue.close()


def test_capture_frame_and_fetch_png_with_auth():
    fake = FakeUE(require_auth=True, auth_token="secret")
    ue = UEClient(
        base_url="http://ue.test",
        transport=make_transport(fake),
        auth_token="secret",
    )
    cmd_result, png = ue.capture_frame(include_image=True)
    assert cmd_result.success is True
    assert png and png.startswith(b"\x89PNG")
    ue.close()
