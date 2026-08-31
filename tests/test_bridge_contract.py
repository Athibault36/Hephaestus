"""Contract tests: tool registry, FakeUE, and documented bridge API stay aligned."""

from __future__ import annotations

import httpx
import pytest

from hephaestus_forge.runtime.config import AUTH_HEADER
from hephaestus_forge.runtime.tools import build_default_registry
from hephaestus_forge.runtime.ue_client import UEClient
from tests.fake_ue import AVAILABLE_COMMANDS, MAX_BODY_BYTES, FakeUE, make_transport


def test_registry_matches_fake_ue_command_surface():
    reg = build_default_registry()
    assert len(reg.names()) == 27
    assert len(AVAILABLE_COMMANDS) == 27
    assert set(reg.names()) == set(AVAILABLE_COMMANDS)


@pytest.mark.parametrize("tool_name,args", [
    ("world.spawn_actor", {"class_path": "/Script/Engine.StaticMeshActor"}),
    ("world.destroy_actor", {"actor_path": "/Game/L.L:PersistentLevel.Cube_1"}),
    ("world.batch_edit", {"actors": ["/Game/L.L:PersistentLevel.Cube_1"]}),
    ("vision.capture_frame", {}),
    ("blueprint.compile", {"blueprint_path": "/Game/BP/BP_Hero.BP_Hero"}),
])
def test_registry_envelopes_accepted_by_fake_ue(tool_name, args):
    fake = FakeUE()
    client = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    reg = build_default_registry()
    result = reg.execute(client, tool_name, args)
    assert result.success is True
    assert fake.received[-1]["command"] in AVAILABLE_COMMANDS
    client.close()


def test_auth_required_on_mutations_not_on_discovery():
    fake = FakeUE(require_auth=True, auth_token="secret")

    def request(method: str, path: str, *, token: str | None = None, body: bytes = b"") -> httpx.Response:
        headers = {AUTH_HEADER: token} if token else {}
        req = httpx.Request(method, f"http://ue.test{path}", headers=headers, content=body)
        return fake.handler(req)

    assert request("GET", "/health").status_code == 200
    assert request("GET", "/commands").status_code == 200
    assert request("POST", "/command", body=b"{}").status_code == 401
    assert request("POST", "/command", token="secret", body=b'{"command":"world.query_spatial","params":{}}').status_code == 200
    assert request("GET", "/frame/1").status_code == 401
    assert request("GET", "/frame/1", token="secret").status_code == 200


def test_batch_endpoint_executes_in_order():
    fake = FakeUE()
    client = UEClient(base_url="http://ue.test", transport=make_transport(fake))
    results = client.execute_batch([
        {"command": "world.query_spatial", "params": {"action": "query_spatial"}},
        {"command": "vision.capture_frame", "params": {"action": "capture_frame"}},
    ])
    assert len(results) == 2
    assert all(r.success for r in results)
    assert len(fake.received) == 2
    client.close()


def test_oversized_payload_returns_413():
    fake = FakeUE(require_auth=True, auth_token="secret")
    body = b"x" * (MAX_BODY_BYTES + 1)
    req = httpx.Request(
        "POST",
        "http://ue.test/command",
        headers={AUTH_HEADER: "secret"},
        content=body,
    )
    resp = fake.handler(req)
    assert resp.status_code == 413
