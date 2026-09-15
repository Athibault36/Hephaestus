# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for the dependency-aware Blender job executor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_jobs import (  # noqa: E402
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_SKIPPED,
    BlenderJob,
    BlenderJobExecutor,
    DependencyError,
    run_job_graph,
)


def _ok_runner(job: BlenderJob):
    return {"success": True, "kind": job.kind}


def test_topo_order_linear_chain():
    ex = BlenderJobExecutor()
    ex.add_many(
        [
            BlenderJob("c", "exec", depends_on=["b"]),
            BlenderJob("b", "exec", depends_on=["a"]),
            BlenderJob("a", "primitive"),
        ]
    )
    assert ex.topo_order() == ["a", "b", "c"]


def test_topo_order_diamond_stable():
    ex = BlenderJobExecutor()
    ex.add_many(
        [
            BlenderJob("base", "primitive"),
            BlenderJob("uv", "exec", depends_on=["base"]),
            BlenderJob("retopo", "exec", depends_on=["base"]),
            BlenderJob("bake", "exec", depends_on=["uv", "retopo"]),
        ]
    )
    order = ex.topo_order()
    assert order.index("base") < order.index("uv")
    assert order.index("base") < order.index("retopo")
    assert order.index("uv") < order.index("bake")
    assert order.index("retopo") < order.index("bake")


def test_cycle_detected():
    ex = BlenderJobExecutor()
    ex.add_many(
        [
            BlenderJob("a", "exec", depends_on=["b"]),
            BlenderJob("b", "exec", depends_on=["a"]),
        ]
    )
    with pytest.raises(DependencyError):
        ex.topo_order()


def test_unknown_dependency_rejected():
    ex = BlenderJobExecutor()
    ex.add(BlenderJob("a", "exec", depends_on=["ghost"]))
    with pytest.raises(DependencyError):
        ex.validate()


def test_duplicate_id_rejected():
    ex = BlenderJobExecutor()
    ex.add(BlenderJob("a", "primitive"))
    with pytest.raises(DependencyError):
        ex.add(BlenderJob("a", "exec"))


def test_run_all_success():
    ex = BlenderJobExecutor()
    ex.add_many(
        [
            BlenderJob("a", "primitive"),
            BlenderJob("b", "exec", depends_on=["a"]),
        ]
    )
    summary = ex.run(_ok_runner)
    assert summary["success"] is True
    assert summary["done"] == ["a", "b"]
    assert summary["failed"] == []


def test_failure_propagates_to_dependents():
    ex = BlenderJobExecutor()
    ex.add_many(
        [
            BlenderJob("base", "primitive"),
            BlenderJob("uv", "exec", depends_on=["base"]),
            BlenderJob("bake", "exec", depends_on=["uv"]),
            BlenderJob("independent", "scene_info"),
        ]
    )

    def runner(job: BlenderJob):
        if job.id == "base":
            return {"success": False, "error": "blender crashed"}
        return {"success": True}

    summary = ex.run(runner)
    assert summary["success"] is False
    assert "base" in summary["failed"]
    # uv and bake depend (transitively) on base → skipped.
    assert set(summary["skipped"]) == {"uv", "bake"}
    # Independent branch still runs.
    assert "independent" in summary["done"]


def test_runner_exception_marks_failed():
    ex = BlenderJobExecutor()
    ex.add(BlenderJob("a", "exec"))

    def boom(job: BlenderJob):
        raise RuntimeError("subprocess died")

    summary = ex.run(boom)
    assert "a" in summary["failed"]
    assert ex.jobs[0].status == STATUS_FAILED
    assert "subprocess died" in ex.jobs[0].error


def test_skipped_status_recorded_on_job():
    ex = BlenderJobExecutor()
    ex.add_many(
        [
            BlenderJob("a", "primitive"),
            BlenderJob("b", "exec", depends_on=["a"]),
        ]
    )
    summary = ex.run(lambda job: {"success": job.id != "a", "error": "x"})
    a = next(j for j in ex.jobs if j.id == "a")
    b = next(j for j in ex.jobs if j.id == "b")
    assert a.status == STATUS_FAILED
    assert b.status == STATUS_SKIPPED
    assert "upstream" in b.error


def test_run_job_graph_convenience():
    jobs = [
        BlenderJob("a", "primitive"),
        BlenderJob("b", "exec", depends_on=["a"]),
    ]
    summary = run_job_graph(jobs, runner=_ok_runner)
    assert summary["success"] is True
    assert summary["order"] == ["a", "b"]


def test_default_dcc_runner_dispatches(monkeypatch):
    import blender_jobs

    captured = {}

    def fake_route(command, params=None):
        captured["command"] = command
        captured["params"] = params
        return {"success": True}

    monkeypatch.setattr("dcc_server.route_command", fake_route, raising=False)
    runner = blender_jobs.default_dcc_runner(project_root="/proj")
    result = runner(BlenderJob("a", "primitive", params={"shape": "cube"}))
    assert result["success"] is True
    assert captured["command"] == "blender.export_fbx"
    assert captured["params"]["project_root"] == "/proj"
    assert captured["params"]["shape"] == "cube"


def test_default_dcc_runner_unknown_kind(monkeypatch):
    import blender_jobs

    monkeypatch.setattr("dcc_server.route_command", lambda c, p=None: {"success": True}, raising=False)
    runner = blender_jobs.default_dcc_runner()
    result = runner(BlenderJob("a", "totally_unknown"))
    assert result["success"] is False
    assert "unknown blender job kind" in result["error"]
