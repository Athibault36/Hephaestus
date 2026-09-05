"""Unit tests for suite asset resolution and PIE wait helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autonomous_suite import (  # noqa: E402
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

    with patch("autonomous_suite._search", side_effect=fake_search):
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

    with patch("autonomous_suite._search", side_effect=fake_search):
        mesh = resolve_suite_static_mesh(client)

    assert mesh.endswith("Cube.Cube")
    assert calls["n"] >= 2


def test_wait_for_pie_returns_true_when_health_ok():
    with patch(
        "preflight_health.fetch_ue_health",
        return_value={"ok": True, "project_name": "X", "project_dir": "C:\\X"},
    ):
        with patch("autonomous_suite.pie_matches_project", create=True):
            with patch(
                "hephaestus_forge.preflight_health.pie_matches_project",
                return_value=(True, "ok"),
            ):
                pass
    with patch("autonomous_suite.fetch_ue_health", create=True):
        pass
    # Patch the import path wait_for_pie uses (preflight_health.*)
    with patch("preflight_health.fetch_ue_health", return_value={"ok": True}):
        with patch("preflight_health.pie_matches_project", return_value=(True, "match")):
            with patch("autonomous_suite._client", return_value=(MagicMock(), lambda e: False)):
                assert wait_for_pie("http://127.0.0.1:8765", timeout_s=1.0, poll_s=0.01) is True


def test_skip_no_character_is_ok():
    from autonomous_suite import SuiteReport, SuiteStepResult, _skip_no_character

    r = _skip_no_character("E2", "blank project")
    assert r.ok is True
    assert r.report.get("skipped") is True
    assert "skipped" in r.detail
    report = SuiteReport(ok=True, steps=[r, SuiteStepResult("H1", True, "world.get_view ok")])
    assert report.skipped_ids == ["E2"]
    assert report.passed_ids == ["H1"]
    assert report.to_dict()["skipped"] == ["E2"]
    assert report.to_dict()["passed"] == ["H1"]


def test_direct_locomotion_uses_transform_when_no_anim():
    from autonomous_suite import _direct_locomotion_suite

    client = MagicMock()
    client.command.side_effect = [
        {"success": True, "actor_paths": ["/Game/World/SK_Actor"], "error": ""},
        {"success": True, "error": "", "result_json": "{}"},
    ]

    with patch(
        "autonomous_suite.resolve_suite_character_assets",
        return_value=("/Engine/EditorMeshes/SkeletalMesh/DefaultSkeletalMesh.DefaultSkeletalMesh", ""),
    ):
        with patch("autonomous_suite._client", return_value=(client, lambda e: False)):
            result = _direct_locomotion_suite("http://127.0.0.1:8765", scenario_id="E2")

    assert result.ok is True
    assert result.report.get("mode") == "transform"
    assert "Transform walk" in result.detail
    cmds = [c.args[0]["command"] for c in client.command.call_args_list]
    assert cmds[0] == "animation.spawn_skeletal_mesh"
    assert cmds[1] == "animation.play_transform_sequence"


def test_scenario_a_is_direct_locomotion():
    from autonomous_suite import SUITE_SCENARIOS

    a = next(s for s in SUITE_SCENARIOS if s.id == "A")
    assert a.kind == "direct"
    assert a.goal == "__suite_locomotion__"
