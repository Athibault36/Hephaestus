# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Hephaestus CC5 OpenPlugin — watches ~/.hephaestus/cc5_jobs for export requests.

Install once into:
  {CC5}/Bin64/OpenPlugin/HephaestusExport/main.py

Requires Character Creator running with a character in the scene.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _jobs_dir() -> Path:
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    d = home / "cc5_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _export_avatar(avatar, out_path: str) -> bool:
    import RLPy

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Prefer modern ExportFbx / ExportFbxFile variants
    try:
        if hasattr(RLPy.RFileIO, "ExportFbxFile"):
            RLPy.RFileIO.ExportFbxFile(avatar, out_path)
            return os.path.isfile(out_path)
    except Exception as exc:
        print(f"HephaestusExport ExportFbxFile: {exc}")
    try:
        if hasattr(RLPy.RFileIO, "ExportFbx"):
            RLPy.RFileIO.ExportFbx(avatar, out_path)
            return os.path.isfile(out_path)
    except Exception as exc:
        print(f"HephaestusExport ExportFbx: {exc}")
    return False


def _process_job(job_path: Path) -> None:
    import RLPy

    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _write_result(job_path, False, error=f"bad job json: {exc}")
        return

    out_path = str(job.get("output_path") or "")
    name_hint = str(job.get("character_name") or "")
    if not out_path:
        _write_result(job_path, False, error="output_path required")
        return

    avatars = []
    try:
        avatars = list(RLPy.RScene.GetAvatars() or [])
    except Exception as exc:
        _write_result(job_path, False, error=f"GetAvatars failed: {exc}")
        return

    avatar = None
    if name_hint:
        for a in avatars:
            try:
                n = a.GetName() if hasattr(a, "GetName") else str(a)
                if n and name_hint.lower() in n.lower():
                    avatar = a
                    break
            except Exception:
                pass
    if avatar is None and avatars:
        avatar = avatars[0]
    if avatar is None:
        _write_result(
            job_path,
            False,
            error="No avatar in CC5 scene — open or create a character first",
        )
        return

    ok = _export_avatar(avatar, out_path)
    if ok:
        _write_result(job_path, True, output_path=out_path)
    else:
        _write_result(
            job_path,
            False,
            error="ExportFbx failed or file missing — check CC5 export API / disk path",
        )


def _write_result(job_path: Path, success: bool, **extra) -> None:
    result = {"success": success, "job": job_path.name, **extra}
    out = job_path.with_suffix(".result.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    try:
        job_path.unlink(missing_ok=True)
    except OSError:
        pass
    print(f"HephaestusExport result -> {out} success={success}")


def _poll_once() -> None:
    jobs = _jobs_dir()
    for job in sorted(jobs.glob("*.job.json")):
        print(f"HephaestusExport processing {job.name}")
        _process_job(job)


# Timer handle kept alive for the CC5 session
_timer = None


def initialize_plugin() -> None:
    """CC5 OpenPlugin entrypoint — start a lightweight poll timer."""
    global _timer
    import RLPy

    print("HephaestusExport: plugin loaded — watching ~/.hephaestus/cc5_jobs")

    # RTimer callback if available; else rely on menu action
    try:
        # Many RLPy builds expose RTimer / QTimer via PySide
        from PySide2 import QtCore  # type: ignore

        app_timer = QtCore.QTimer()
        app_timer.setInterval(1500)
        app_timer.timeout.connect(_poll_once)
        app_timer.start()
        _timer = app_timer
    except Exception as exc:
        print(f"HephaestusExport: QTimer unavailable ({exc}) — use Plugins > Hephaestus > Process export jobs")

    try:
        RLPy.RUi.AddMenu("Hephaestus", RLPy.EMenu_Plugins)
    except Exception:
        pass
    try:
        # Best-effort menu action
        pass
    except Exception:
        pass

    _poll_once()
