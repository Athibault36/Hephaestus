# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Session lifecycle for CC5 studio control."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .audit import audit_log
from .capabilities import INTEGRATOR_VERSION, capability_report

_SESSION: dict[str, Any] = {
    "active": False,
    "engine_backend": None,
    "config": {},
    "snapshot": None,
    "project_root": None,
    "started_at": None,
}


def _session_store() -> Path:
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    home.mkdir(parents=True, exist_ok=True)
    return home / "cc5_studio_session.json"


def _persist() -> None:
    _session_store().write_text(json.dumps(_SESSION, indent=2, default=str), encoding="utf-8")


def get_session() -> dict[str, Any]:
    return dict(_SESSION)


def initialize_cc5_session(
    engine_backend: str = "ue58",
    config_json: Optional[dict[str, Any] | str] = None,
) -> dict[str, Any]:
    """
    Start a studio↔CC5 control session.

    engine_backend: only ``ue58`` is supported (HephaestusBridge).
    config_json: dict or JSON string — may include project_root, dismiss_dialogs.
    """
    if isinstance(config_json, str):
        config = json.loads(config_json) if config_json.strip() else {}
    else:
        config = dict(config_json or {})

    backend = (engine_backend or "ue58").strip().lower()
    if backend not in ("ue58", "unreal", "ue5", "ue"):
        err = f"unsupported engine_backend={engine_backend!r}; use ue58"
        audit_log("initialize_cc5_session", ok=False, error=err)
        return {"ok": False, "error": err, "capabilities": capability_report()}

    try:
        from cc5_bridge import ensure_cc5_running, find_cc5, install_cc5_openplugin
    except ImportError:
        from hephaestus_forge.cc5_bridge import (  # type: ignore
            ensure_cc5_running,
            find_cc5,
            install_cc5_openplugin,
        )

    if not find_cc5():
        err = "cc5_unavailable — install Character Creator 5"
        audit_log("initialize_cc5_session", ok=False, error=err)
        return {"ok": False, "error": err}

    plugin = install_cc5_openplugin(force=bool(config.get("force_plugin_install", False)))
    launched = ensure_cc5_running(wait_s=float(config.get("cc5_wait_s") or 8.0))

    if config.get("dismiss_dialogs", True):
        try:
            from dialog_control import auto_dismiss
        except ImportError:
            try:
                from hephaestus_forge.dialog_control import auto_dismiss  # type: ignore
            except ImportError:
                auto_dismiss = None  # type: ignore
        if auto_dismiss:
            try:
                auto_dismiss(only_known=False, target_processes_only=True)
            except Exception:
                pass

    project_root = config.get("project_root")
    _SESSION.update(
        {
            "active": True,
            "engine_backend": "ue58",
            "config": config,
            "snapshot": {
                "t": time.time(),
                "plugin": {k: plugin.get(k) for k in ("ok", "detail", "live_path", "path")},
            },
            "project_root": str(project_root) if project_root else None,
            "started_at": time.time(),
            "integrator_version": INTEGRATOR_VERSION,
        }
    )
    _persist()
    out = {
        "ok": True,
        "engine_backend": "ue58",
        "cc5": launched,
        "plugin": plugin,
        "session": get_session(),
        "capabilities": capability_report(),
    }
    audit_log("initialize_cc5_session", ok=True, detail={"plugin_detail": plugin.get("detail")})
    return out


def terminate_cc5_session() -> dict[str, Any]:
    """Clean detach: persist snapshot, clear active flag (does not kill CC5)."""
    snap = dict(_SESSION)
    _SESSION.update(
        {
            "active": False,
            "snapshot": {"t": time.time(), "prior": snap.get("snapshot"), "ended": True},
        }
    )
    _persist()
    audit_log("terminate_cc5_session", ok=True)
    return {"ok": True, "session": get_session()}


def detach_cc5_control(reason: str = "emergency_stop") -> dict[str, Any]:
    """
    Fallback/emergency stop: hand control back (stop forcing dialogs), save state, log cause.

    Does not quit Character Creator — operators keep the GUI; studio stops owning the session.
    """
    _SESSION["active"] = False
    _SESSION["detach_reason"] = reason
    _SESSION["detached_at"] = time.time()
    _persist()
    audit_log("detach_cc5_control", ok=True, detail={"reason": reason})
    return {
        "ok": True,
        "reason": reason,
        "message": "Studio control detached; CC5 UI remains for manual use",
        "session": get_session(),
    }


def rollback_cc5_configuration() -> dict[str, Any]:
    """Restore last session snapshot metadata (re-apply on next configure_character)."""
    store = _session_store()
    if not store.is_file():
        return {"ok": False, "error": "no_session_snapshot"}
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"corrupt_snapshot: {exc}"}
    snap = data.get("snapshot") or data
    _SESSION["rollback_target"] = snap
    _persist()
    audit_log("rollback_cc5_configuration", ok=True)
    return {"ok": True, "rollback_target": snap}
