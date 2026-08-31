import httpx
import pytest

from hephaestus_forge.runtime.ue_client import CommandResult, UEClient, UEConnectionError
from tests.fake_ue import FakeUE, make_transport


def make_client(fake: FakeUE) -> UEClient:
    return UEClient(base_url="http://ue.test", transport=make_transport(fake), max_retries=2)


def test_health_and_commands():
    fake = FakeUE()
    client = make_client(fake)
    assert client.is_healthy() is True
    assert "world.spawn_actor" in client.available_commands()


def test_execute_success_parses_result_and_actors():
    fake = FakeUE()
    client = make_client(fake)
    result = client.execute(
        "world.spawn_actor",
        {"action": "spawn_actor", "class_path": "/Script/Engine.StaticMeshActor"},
    )
    assert isinstance(result, CommandResult)
    assert result.success is True
    assert result.result["actor_path"].endswith("SpawnedActor_1")
    assert result.actor_references and "SpawnedActor_1" in result.actor_references[0]
    # The envelope reached the fake exactly as constructed.
    assert fake.received[-1]["command"] == "world.spawn_actor"


def test_command_failure_is_returned_not_raised():
    fake = FakeUE()
    client = make_client(fake)
    result = client.execute("world.spawn_actor", {"action": "spawn_actor"})  # no class_path
    assert result.success is False
    assert "class_path" in result.error_message


def test_transient_5xx_is_retried_then_succeeds():
    fake = FakeUE()
    fake.fail_transport_times = 2  # first two calls return 503, third succeeds
    client = make_client(fake)
    result = client.execute("vision.capture_frame", {"action": "capture_frame"})
    assert result.success is True
    assert result.result["frame_id"] == 1


def test_connection_error_raises():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = UEClient(base_url="http://ue.test", transport=httpx.MockTransport(boom), max_retries=1)
    with pytest.raises(UEConnectionError):
        client.execute("vision.capture_frame", {"action": "capture_frame"})


def test_batch_execution():
    fake = FakeUE()
    client = make_client(fake)
    results = client.execute_batch(
        [
            {"command": "vision.capture_frame", "params": {"action": "capture_frame"}},
            {"command": "world.query_spatial", "params": {"action": "query_spatial"}},
        ]
    )
    assert len(results) == 2
    assert all(r.success for r in results)


def test_result_from_response_field_aliases():
    # Accept PascalCase (raw USTRUCT) field names too.
    r = CommandResult.from_response(
        {"bSuccess": True, "ResultJSON": '{"k": 1}', "ActorReferences": ["A"], "CommandID": "cmd_9"}
    )
    assert r.success and r.result == {"k": 1} and r.actor_references == ["A"] and r.command_id == "cmd_9"
