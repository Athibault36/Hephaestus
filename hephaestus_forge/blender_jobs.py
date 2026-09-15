# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Dependency-aware Blender job executor (factory side).

The DCC plane can run one-shot Blender commands, but multi-step authoring
(e.g. build base mesh → retopo → UV → bake → export) needs ordering and
failure propagation. This module owns that scheduling: a small DAG of
:class:`BlenderJob` nodes executed in topological order via an injected
runner, so a dependent job is skipped when any upstream job fails.

Pure Python + dependency-injected runner → fully unit-testable without a
Blender install. The default runner dispatches through the DCC control plane
(``blender.*`` commands), letting a persistent Blender session (when one is
available) service the whole graph.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# Runner contract: given a BlenderJob, return a dict with at least {"success": bool}.
JobRunner = Callable[["BlenderJob"], Dict[str, Any]]


@dataclass
class BlenderJob:
    """One node in a Blender authoring DAG."""

    id: str
    kind: str  # e.g. "primitive", "creature", "exec", "scene_info"
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: str = STATUS_PENDING
    result: Optional[Dict[str, Any]] = None
    error: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "params": dict(self.params),
            "depends_on": list(self.depends_on),
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


class DependencyError(ValueError):
    """Raised for cycles or references to unknown job ids."""


class BlenderJobExecutor:
    """Schedules a Blender job DAG with dependency ordering + failure gating."""

    def __init__(self) -> None:
        self._jobs: Dict[str, BlenderJob] = {}
        self._order: List[str] = []  # insertion order for stable tie-breaking

    def add(self, job: BlenderJob) -> BlenderJob:
        if job.id in self._jobs:
            raise DependencyError(f"duplicate job id: {job.id}")
        self._jobs[job.id] = job
        self._order.append(job.id)
        return job

    def add_many(self, jobs: Sequence[BlenderJob]) -> None:
        for job in jobs:
            self.add(job)

    @property
    def jobs(self) -> List[BlenderJob]:
        return [self._jobs[jid] for jid in self._order]

    def validate(self) -> None:
        """Raise DependencyError on unknown deps or cycles."""
        for job in self._jobs.values():
            for dep in job.depends_on:
                if dep not in self._jobs:
                    raise DependencyError(
                        f"job {job.id!r} depends on unknown job {dep!r}"
                    )
        self.topo_order()  # raises on cycle

    def topo_order(self) -> List[str]:
        """
        Kahn topological sort, insertion-order-stable.

        Returns job ids in an order where every dependency precedes its
        dependents. Raises DependencyError on a cycle.
        """
        indegree: Dict[str, int] = {jid: 0 for jid in self._order}
        dependents: Dict[str, List[str]] = {jid: [] for jid in self._order}
        for jid in self._order:
            for dep in self._jobs[jid].depends_on:
                if dep not in self._jobs:
                    raise DependencyError(f"job {jid!r} depends on unknown job {dep!r}")
                indegree[jid] += 1
                dependents[dep].append(jid)

        # Seed with zero-indegree nodes in insertion order (stable).
        ready = [jid for jid in self._order if indegree[jid] == 0]
        ordered: List[str] = []
        while ready:
            jid = ready.pop(0)
            ordered.append(jid)
            for child in dependents[jid]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)

        if len(ordered) != len(self._order):
            remaining = [jid for jid in self._order if jid not in ordered]
            raise DependencyError(f"dependency cycle among: {remaining}")
        return ordered

    def run(self, runner: JobRunner) -> Dict[str, Any]:
        """
        Execute the DAG in topological order.

        A job is skipped (STATUS_SKIPPED) when any of its transitive
        dependencies failed or was skipped — failure propagates downstream
        rather than running work whose inputs never materialised.
        """
        self.validate()
        order = self.topo_order()
        failed_or_skipped: set[str] = set()

        for jid in order:
            job = self._jobs[jid]
            blocked = [d for d in job.depends_on if d in failed_or_skipped]
            if blocked:
                job.status = STATUS_SKIPPED
                job.error = f"skipped — upstream not satisfied: {', '.join(blocked)}"
                failed_or_skipped.add(jid)
                continue

            job.status = STATUS_RUNNING
            job.started_at = time.time()
            try:
                result = runner(job)
            except Exception as exc:  # runner raised — treat as failure
                job.status = STATUS_FAILED
                job.error = str(exc)
                job.finished_at = time.time()
                failed_or_skipped.add(jid)
                continue
            job.result = result
            job.finished_at = time.time()
            if result and result.get("success"):
                job.status = STATUS_DONE
            else:
                job.status = STATUS_FAILED
                job.error = (result or {}).get("error", "job reported failure")
                failed_or_skipped.add(jid)

        done = [j.id for j in self.jobs if j.status == STATUS_DONE]
        failed = [j.id for j in self.jobs if j.status == STATUS_FAILED]
        skipped = [j.id for j in self.jobs if j.status == STATUS_SKIPPED]
        return {
            "success": not failed and not skipped,
            "total": len(self._jobs),
            "done": done,
            "failed": failed,
            "skipped": skipped,
            "order": order,
            "jobs": [j.to_dict() for j in self.jobs],
        }


def default_dcc_runner(project_root: Optional[str] = None) -> JobRunner:
    """
    Build a runner that dispatches jobs through the DCC control plane.

    Maps ``job.kind`` → ``blender.*`` DCC commands. Kept lazy so importing this
    module never requires the DCC server or Blender to be present.
    """
    try:
        from dcc_server import route_command
    except ImportError:  # pragma: no cover - namespaced import fallback
        from hephaestus_forge.dcc_server import route_command  # type: ignore

    _KIND_TO_COMMAND = {
        "primitive": "blender.export_fbx",
        "export_fbx": "blender.export_fbx",
        "creature": "blender.export_creature",
        "exec": "blender.exec",
        "scene_info": "blender.scene_info",
    }

    def _run(job: BlenderJob) -> Dict[str, Any]:
        command = _KIND_TO_COMMAND.get(job.kind)
        if command is None:
            return {"success": False, "error": f"unknown blender job kind: {job.kind}"}
        params = dict(job.params)
        if project_root and "project_root" not in params:
            params["project_root"] = project_root
        return route_command(command, params)

    return _run


def run_job_graph(
    jobs: Sequence[BlenderJob],
    runner: Optional[JobRunner] = None,
    *,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience: build an executor, run the graph, return the summary."""
    executor = BlenderJobExecutor()
    executor.add_many(jobs)
    active_runner = runner or default_dcc_runner(project_root)
    return executor.run(active_runner)
