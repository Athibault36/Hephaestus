# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Engage / disengage UE PIE via the editor control API (:8766) and PIE API (:8765)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_EDITOR_API = "http://127.0.0.1:8766"
DEFAULT_PIE_API = "http://127.0.0.1:8765"


def editor_api_base() -> str:
    return (os.environ.get("HEPHAESTUS_EDITOR_API") or DEFAULT_EDITOR_API).rstrip("/")


def pie_api_base() -> str:
    return (os.environ.get("HEPHAESTUS_UE_API") or DEFAULT_PIE_API).rstrip("/")


def _get_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8") or "{}")


def _post_command(base: str, command: str, params: Optional[dict[str, Any]] = None, timeout: float = 10.0) -> dict[str, Any]:
    body = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/command",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8") or ""
        except Exception:
            raw = ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict) and parsed:
            # Preserve bridge error payload (e.g. unknown command on stale DLL).
            parsed.setdefault("success", False)
            if not parsed.get("error"):
                parsed["error"] = raw or f"HTTP {exc.code}"
            return parsed
        return {"success": False, "error": raw or f"HTTP {exc.code}: {exc.reason}"}


def fetch_editor_health(timeout: float = 2.0) -> dict[str, Any]:
    return _get_json(editor_api_base() + "/v1/health", timeout=timeout)


def fetch_pie_health(timeout: float = 2.0) -> dict[str, Any]:
    try:
        from preflight_health import fetch_ue_health
    except ImportError:
        from hephaestus_forge.preflight_health import fetch_ue_health  # type: ignore
    return fetch_ue_health(pie_api_base(), timeout=timeout)


def editor_online(timeout: float = 1.5) -> tuple[bool, dict[str, Any], str]:
    try:
        health = fetch_editor_health(timeout=timeout)
        if not health.get("ok"):
            return False, health, "editor health ok=false"
        return True, health, f"editor online (port {health.get('port', 8766)})"
    except Exception as exc:
        return False, {}, f"editor offline at {editor_api_base()}/v1/health ({exc})"


def pie_online(timeout: float = 1.5) -> tuple[bool, dict[str, Any], str]:
    try:
        health = fetch_pie_health(timeout=timeout)
        if not health.get("ok"):
            return False, health, "PIE health ok=false"
        return True, health, f"PIE online (plugin {health.get('plugin_version', '?')})"
    except Exception as exc:
        return False, {}, f"PIE offline at {pie_api_base()}/v1/health ({exc})"


def play() -> dict[str, Any]:
    """Request PIE start via editor :8766."""
    return _post_command(editor_api_base(), "editor.play")


def stop() -> dict[str, Any]:
    """Stop PIE via editor :8766, falling back to PIE :8765 editor.stop."""
    ok, _, _ = editor_online()
    if ok:
        return _post_command(editor_api_base(), "editor.stop")
    pie_ok, pie_health, _ = pie_online()
    if pie_ok:
        result = _post_command(pie_api_base(), "editor.stop")
        err = str(result.get("error") or "")
        if not result.get("success") and "Unknown command" in err:
            ver = pie_health.get("plugin_version") or "?"
            result["error"] = (
                f"{err} — live PIE plugin is {ver}; forge sync-plugin, rebuild "
                f"HephaestusBridge 1.0.1+, full editor restart (or Stop Play manually). "
                f"Editor API :8766 is also offline until that rebuild."
            )
        return result
    raise RuntimeError(
        f"Neither editor API ({editor_api_base()}) nor PIE API ({pie_api_base()}) is reachable. "
        f"Open the .uproject with HephaestusBridge ≥1.0.1 rebuilt, or Stop Play in the editor."
    )


def wait_for_pie(
    project_root: Optional[Path] = None,
    *,
    timeout_s: float = 45.0,
    poll_s: float = 1.0,
) -> tuple[bool, dict[str, Any], str]:
    """Poll PIE :8765 until healthy (and identity matches when project_root given)."""
    try:
        from preflight_health import fetch_ue_health, pie_matches_project
    except ImportError:
        from hephaestus_forge.preflight_health import fetch_ue_health, pie_matches_project  # type: ignore

    deadline = time.time() + timeout_s
    last_detail = "waiting for PIE"
    last_health: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            health = fetch_ue_health(pie_api_base(), timeout=2.0)
            last_health = health
            if not health.get("ok"):
                last_detail = "PIE health ok=false"
                time.sleep(poll_s)
                continue
            if project_root is not None:
                match_ok, match_detail = pie_matches_project(health, Path(project_root))
                if not match_ok:
                    last_detail = match_detail
                    time.sleep(poll_s)
                    continue
                return True, health, match_detail
            return True, health, f"PIE online ({health.get('project_name') or health.get('service')})"
        except Exception as exc:
            last_detail = str(exc)
        time.sleep(poll_s)
    return False, last_health, last_detail


def status_snapshot(project_root: Optional[Path] = None) -> dict[str, Any]:
    ed_ok, ed_health, ed_detail = editor_online()
    pie_ok, pie_health, pie_detail = pie_online()
    identity = ""
    if pie_ok and project_root is not None:
        try:
            from preflight_health import pie_matches_project
        except ImportError:
            from hephaestus_forge.preflight_health import pie_matches_project  # type: ignore
        match_ok, match_detail = pie_matches_project(pie_health, Path(project_root))
        identity = match_detail if match_ok else match_detail
        if not match_ok:
            pie_ok = False
            pie_detail = match_detail
    return {
        "editor_api": editor_api_base(),
        "pie_api": pie_api_base(),
        "editor_online": ed_ok,
        "editor_detail": ed_detail,
        "editor_health": ed_health,
        "pie_online": pie_ok,
        "pie_detail": pie_detail,
        "pie_health": pie_health,
        "identity": identity,
        "project_root": str(Path(project_root).resolve()) if project_root else "",
    }
