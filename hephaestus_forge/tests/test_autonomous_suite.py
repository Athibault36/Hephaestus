"""Unit tests for suite asset resolution and PIE wait helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hephaestus_forge.autonomous_suite import (
    resolve_suite_character_assets,
    resolve_suite_static_mesh,
    wait_for_pie,
)


def test_resolve_suite_character_assets_prefers_skeletal_and_walk():
    client = MagicMock()

    def fake_search(_client, query, asset_class="", limit=8):
        if asset_class == "SkeletalMesh":
            return [
                "/Game/Chars/Beverly/Anims/Walk.AnimSequence",
                "/Game/Chars/Beverly/Beverly_SK.Beverly_SK",
            ]
        if asset_class == "AnimSequence":
            return [
                "/Game/Chars/Beverly/Anims/Idle.AnimSequence",
                "/Game/Chars/Beverly/Anims/Walk.AnimSequence",
            ]
        return []

    with patch("hephaestus_forge.autonomous_suite._search", side_effect=fake_search):
        mesh, anim = resolve_suite_character_assets(client)

    assert "Beverly_SK" in mesh
    assert "Walk" in anim
    assert ".AnimSequence" not in mesh


def test_resolve_suite_static_mesh_skips_materials():
    client = MagicMock()
    calls = {"n": 0}

    def fake_search(_client, query, asset_class="", limit=8):
        calls["n"] += 1
        if query == "Dog":
            return ["/Game/Mats/Dog.Material"]
        if query == "Cube":
            return ["/Engine/BasicShapes/Cube.Cube"]
        return []

    with patch("hephaestus_forge.autonomous_suite._search", side_effect=fake_search):
        mesh = resolve_suite_static_mesh(client)

    assert mesh.endswith("Cube.Cube")
    assert calls["n"] >= 2


def test_wait_for_pie_returns_true_when_health_ok():
    client = MagicMock()
    client.health.return_value = {"ok": True}
    with patch("hephaestus_forge.autonomous_suite._client", return_value=(client, lambda e: False)):
        assert wait_for_pie("http://127.0.0.1:8765", timeout_s=1.0, poll_s=0.01) is True


def test_wait_for_pie_retries_connection_errors_then_ok():
    client = MagicMock()
    client.health.side_effect = [
        ConnectionError("10061 actively refused"),
        {"ok": True},
    ]
    is_conn = lambda e: "10061" in str(e)
    with patch("hephaestus_forge.autonomous_suite._client", return_value=(client, is_conn)):
        with patch("hephaestus_forge.autonomous_suite.time.sleep"):
            assert wait_for_pie("http://127.0.0.1:8765", timeout_s=5.0, poll_s=0.01) is True
    assert client.health.call_count == 2
