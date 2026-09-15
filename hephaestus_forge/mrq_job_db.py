# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Movie Render Queue (MRQ) job database — power-off-safe persistence for
Hephaestus render jobs.

This is the factory-side "brain" the UE bridge executor reports into. It is a
pure-Python, crash-resilient store (one atomically-written JSON file per job)
so that a machine losing power mid-render can, on restart, detect interrupted
jobs and re-submit the UE MoviePipeline executor from the last completed frame.

Lifecycle::

    QUEUED --submit--> SUBMITTED --attach_executor--> RENDERING
        RENDERING --update_progress(frame)--> RENDERING
        RENDERING --mark_done--> DONE
        RENDERING --mark_failed--> FAILED
    (process death while SUBMITTED/RENDERING) --recover--> INTERRUPTED
        INTERRUPTED --resume--> SUBMITTED (resume_count += 1)

No ``unreal`` import: the UE executor pushes ``executor_job_id`` and per-frame
progress here; this module owns durability, recovery, and resume math.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

STATUS_QUEUED = "queued"
STATUS_SUBMITTED = "submitted"
STATUS_RENDERING = "rendering"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"

# States that mean "in flight" — a crash while in these is recoverable.
_IN_FLIGHT = frozenset({STATUS_SUBMITTED, STATUS_RENDERING})
_TERMINAL = frozenset({STATUS_DONE, STATUS_FAILED})


@dataclass
class MrqJob:
    """One Movie Render Queue job, persisted as a single JSON document."""

    job_id: str
    sequence_path: str
    output_dir: str
    status: str = STATUS_QUEUED
    executor_job_id: str = ""
    config_path: str = ""
    preset_path: str = ""
    total_frames: int = 0
    current_frame: int = 0
    resume_count: int = 0
    error: str = ""
    label: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    @property
    def progress(self) -> float:
        """Fraction complete in [0, 1] (0 when total is unknown)."""
        if self.total_frames <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current_frame / float(self.total_frames)))

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    @property
    def is_in_flight(self) -> bool:
        return self.status in _IN_FLIGHT

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["progress"] = self.progress
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MrqJob":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class MrqJobDb:
    """
    Filesystem-backed MRQ job store.

    Each job lives at ``{root}/{job_id}.json`` and is written atomically
    (temp file + ``os.replace``) so an interrupted write never corrupts an
    existing record. The directory *is* the index — no central manifest to
    fall out of sync.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- storage helpers ------------------------------------------------------

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _write(self, job: MrqJob) -> None:
        job.updated_at = time.time()
        target = self._path(job.job_id)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(job.to_dict(), fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def get(self, job_id: str) -> Optional[MrqJob]:
        path = self._path(job_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (json.JSONDecodeError, OSError):
            return None
        return MrqJob.from_dict(data)

    def list_jobs(self, status: Optional[str] = None) -> List[MrqJob]:
        jobs: List[MrqJob] = []
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            except (json.JSONDecodeError, OSError):
                continue
            job = MrqJob.from_dict(data)
            if status is None or job.status == status:
                jobs.append(job)
        jobs.sort(key=lambda j: j.created_at)
        return jobs

    # -- lifecycle ------------------------------------------------------------

    def submit(
        self,
        sequence_path: str,
        output_dir: str,
        *,
        total_frames: int = 0,
        config_path: str = "",
        preset_path: str = "",
        label: str = "",
        job_id: Optional[str] = None,
    ) -> MrqJob:
        """Record a new render submission (status SUBMITTED)."""
        job = MrqJob(
            job_id=job_id or uuid.uuid4().hex[:12],
            sequence_path=sequence_path,
            output_dir=output_dir,
            status=STATUS_SUBMITTED,
            total_frames=int(total_frames),
            config_path=config_path,
            preset_path=preset_path,
            label=label or Path(sequence_path).stem,
        )
        self._write(job)
        return job

    def attach_executor(self, job_id: str, executor_job_id: str) -> Optional[MrqJob]:
        """Wire the UE bridge executor's job id and move to RENDERING."""
        job = self.get(job_id)
        if job is None:
            return None
        job.executor_job_id = executor_job_id
        if job.status in (STATUS_SUBMITTED, STATUS_INTERRUPTED, STATUS_QUEUED):
            job.status = STATUS_RENDERING
        self._write(job)
        return job

    def update_progress(
        self,
        job_id: str,
        current_frame: int,
        total_frames: Optional[int] = None,
    ) -> Optional[MrqJob]:
        """Per-frame callback from the UE executor; persisted for power-off resume."""
        job = self.get(job_id)
        if job is None:
            return None
        if total_frames is not None:
            job.total_frames = int(total_frames)
        job.current_frame = max(job.current_frame, int(current_frame))
        if job.status not in _TERMINAL:
            job.status = STATUS_RENDERING
        self._write(job)
        return job

    def mark_done(self, job_id: str) -> Optional[MrqJob]:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = STATUS_DONE
        if job.total_frames:
            job.current_frame = job.total_frames
        job.finished_at = time.time()
        job.error = ""
        self._write(job)
        return job

    def mark_failed(self, job_id: str, error: str = "") -> Optional[MrqJob]:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = STATUS_FAILED
        job.error = error
        job.finished_at = time.time()
        self._write(job)
        return job

    # -- crash recovery + resume ---------------------------------------------

    def recover(self) -> List[MrqJob]:
        """
        Mark every in-flight job as INTERRUPTED (call once on startup).

        Returns the jobs that were transitioned — these are candidates for
        :meth:`resume`. Idempotent: already-interrupted/terminal jobs untouched.
        """
        interrupted: List[MrqJob] = []
        for job in self.list_jobs():
            if job.is_in_flight:
                job.status = STATUS_INTERRUPTED
                self._write(job)
                interrupted.append(job)
        return interrupted

    def resume(self, job_id: str) -> Optional[MrqJob]:
        """
        Prepare an interrupted job for re-submission to the UE executor.

        Moves INTERRUPTED → SUBMITTED, clears the stale executor id, bumps
        ``resume_count``, and keeps ``current_frame`` as the resume point so the
        executor can skip already-rendered frames.
        """
        job = self.get(job_id)
        if job is None:
            return None
        if job.status != STATUS_INTERRUPTED:
            return job
        job.status = STATUS_SUBMITTED
        job.executor_job_id = ""
        job.resume_count += 1
        job.error = ""
        self._write(job)
        return job

    def resume_frame(self, job_id: str) -> int:
        """The frame index the executor should resume from (0-based)."""
        job = self.get(job_id)
        if job is None:
            return 0
        return job.current_frame

    def prune(self, max_age_sec: float = 7 * 24 * 3600.0) -> int:
        """Delete terminal jobs older than max_age_sec. Returns count removed."""
        removed = 0
        cutoff = time.time() - max_age_sec
        for job in self.list_jobs():
            age_ref = job.finished_at if job.finished_at is not None else job.updated_at
            if job.is_terminal and age_ref < cutoff:
                try:
                    self._path(job.job_id).unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
        return removed


def default_job_db_dir(project_root: Optional[Path] = None) -> Path:
    """
    Target-agnostic MRQ job DB location.

    Preferred: ``{project}/.hephaestus_forge/mrq_jobs``.
    Fallback:  ``{cwd}/.hephaestus_forge/mrq_jobs``.
    """
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    return root / ".hephaestus_forge" / "mrq_jobs"
