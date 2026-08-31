"""Tests for run_soak helper."""

from hephaestus_forge.runtime.llm import LLMResponse
from hephaestus_forge.runtime.orchestrator import AgentRuntime
from hephaestus_forge.runtime.soak import run_soak
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import FakeUE, make_transport


def test_run_soak_repeat_three():
    fake = FakeUE()
    ue = UEClient(base_url="http://ue.test", transport=make_transport(fake))

    class Finisher:
        def chat(self, messages, tools=None):
            return LLMResponse(content="all good")

    runtime = AgentRuntime(Finisher(), ue, build_default_registry(), max_steps=2)
    runs = run_soak(runtime, "ping", repeat=3)
    assert len(runs) == 3
    assert all(r.completed for r in runs)
    ue.close()
