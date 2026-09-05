# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""HTTP client for the Hephaestus DCC control plane (:8084)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_DCC_API = "http://127.0.0.1:8084"


def dcc_api_base() -> str:
    return (os.environ.get("HEPHAESTUS_DCC_API") or DEFAULT_DCC_API).rstrip("/")


class DccClient:
    """Thin client mirroring RemoteUeClient.command / health style."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 120.0):
        self.base_url = (base_url or dcc_api_base()).rstrip("/")
        self.timeout = timeout

    def health(self, timeout: Optional[float] = None) -> dict[str, Any]:
        url = self.base_url + "/v1/health"
        with urllib.request.urlopen(url, timeout=timeout or min(self.timeout, 5.0)) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def command(self, command: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        body = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/v1/command",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
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
                parsed.setdefault("success", False)
                return parsed
            return {"success": False, "error": raw or f"HTTP {exc.code}"}


def dcc_online(timeout: float = 1.5) -> tuple[bool, dict[str, Any], str]:
    try:
        health = DccClient().health(timeout=timeout)
        if not health.get("ok"):
            return False, health, "DCC health ok=false"
        ready = bool(health.get("ready"))
        blender = health.get("blender") or {}
        detail = (
            f"DCC online (port {health.get('port', 8084)}; "
            f"blender={'yes' if blender.get('available') else 'no'}"
        )
        if blender.get("version"):
            detail += f" {blender.get('version')}"
        detail += ")"
        return True, health, detail if ready or health.get("ok") else detail + " — Blender missing"
    except Exception as exc:
        return False, {}, f"DCC offline at {dcc_api_base()}/v1/health ({exc})"


def start_dcc_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8084,
    wait_s: float = 15.0,
) -> dict[str, Any]:
    """Spawn `python -m hephaestus_forge.dcc_server` in background; wait until health ok."""
    ok, health, detail = dcc_online()
    if ok:
        return {"ok": True, "launched": False, "detail": detail, "health": health, "pid": None}

    env = os.environ.copy()
    env["DCC_BRIDGE_HOST"] = host
    env["DCC_BRIDGE_PORT"] = str(port)
    env["HEPHAESTUS_DCC_API"] = f"http://{host}:{port}"

    # Prefer package module so factory install works.
    cmd = [sys.executable, "-m", "hephaestus_forge.dcc_server"]
    # Fallback: run file if package module fails on some installs
    try:
        import hephaestus_forge.dcc_server  # noqa: F401
    except ImportError:
        here = Path(__file__).resolve().parent / "dcc_server.py"
        cmd = [sys.executable, str(here)]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags if sys.platform == "win32" else 0,
        start_new_session=(sys.platform != "win32"),
    )

    deadline = time.time() + wait_s
    last = "waiting for DCC"
    last_health: dict[str, Any] = {}
    while time.time() < deadline:
        ok, health, detail = dcc_online()
        last_health = health
        last = detail
        if ok:
            return {
                "ok": True,
                "launched": True,
                "pid": proc.pid,
                "detail": detail,
                "health": health,
            }
        if proc.poll() is not None:
            return {
                "ok": False,
                "launched": True,
                "pid": proc.pid,
                "error": f"DCC server exited early (code {proc.returncode})",
                "detail": last,
            }
        time.sleep(0.4)

    return {
        "ok": False,
        "launched": True,
        "pid": proc.pid,
        "error": f"DCC server did not become ready in {wait_s}s ({last})",
        "health": last_health,
        "detail": last,
    }
