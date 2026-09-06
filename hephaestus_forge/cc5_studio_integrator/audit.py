# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Append-only audit trail for CC5 studio integrator calls."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def _audit_dir() -> Path:
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    d = home / "cc5_audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def audit_log(
    event: str,
    *,
    ok: bool = True,
    detail: Optional[dict[str, Any]] = None,
    error: str = "",
) -> Path:
    """Append one JSONL record; returns the log file path."""
    day = time.strftime("%Y%m%d")
    path = _audit_dir() / f"cc5_studio_{day}.jsonl"
    rec = {
        "t": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
        "ok": bool(ok),
        "error": error or "",
        "detail": detail or {},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
    return path
