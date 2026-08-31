import pytest

from hephaestus_forge.runtime.auth import extract_token_from_headers, validate_bridge_token
from hephaestus_forge.runtime.ue_client import UEClient, UEConnectionError
from tests.fake_ue import FakeUE, make_transport


def test_ue_client_sends_auth_header():
    fake = FakeUE(require_auth=True, auth_token="abc")
    client = UEClient(base_url="http://ue.test", transport=make_transport(fake), auth_token="abc")
    assert client.is_healthy() is True
    client.close()


def test_ue_client_auth_rejected():
    fake = FakeUE(require_auth=True, auth_token="abc")
    client = UEClient(base_url="http://ue.test", transport=make_transport(fake), auth_token="wrong")
    with pytest.raises(UEConnectionError):
        client.health()
    client.close()


def test_validate_bridge_token_optional():
    assert validate_bridge_token(require_auth=False, expected=None, provided=None) is True


def test_validate_bridge_token_required():
    assert validate_bridge_token(require_auth=True, expected="tok", provided="tok") is True
    assert validate_bridge_token(require_auth=True, expected="tok", provided="nope") is False
    assert validate_bridge_token(require_auth=True, expected="", provided="tok") is False


def test_extract_token_from_headers():
    assert extract_token_from_headers({"X-Hephaestus-Token": "x"}) == "x"
    assert extract_token_from_headers({}) is None
