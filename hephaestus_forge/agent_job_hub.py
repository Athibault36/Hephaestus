# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Background agent jobs — chat/loop return immediately while work continues."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Optional


class AgentJobHub:
    """In-process job tracker for non-blocking Mission Control runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, label: str, fn: Callable[[], dict[str, Any]]) -> str:
        self.prune()
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "label": label,
                "status": "running",
                "started_at": time.time(),
                "finished_at": None,
                "result": None,
                "error": "",
            }

        def _run() -> None:
            try:
                result = fn()
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["status"] = "done"
                        job["result"] = result
                        job["finished_at"] = time.time()
            except Exception as exc:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["status"] = "error"
                        job["error"] = str(exc)
                        job["finished_at"] = time.time()

        threading.Thread(target=_run, name=f"hephaestus-job-{job_id}", daemon=True).start()
        return job_id

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def prune(self, max_age_sec: float = 3600.0) -> int:
        cutoff = time.time() - max_age_sec
        removed = 0
        with self._lock:
            dead = [
                jid
                for jid, job in self._jobs.items()
                if job.get("finished_at") and job["finished_at"] < cutoff
            ]
            for jid in dead:
                del self._jobs[jid]
                removed += 1
        return removed
