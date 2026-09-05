# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Hands-off Unreal Editor launch + forge up/down orchestration."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from pie_control import (
        editor_online,
        pie_online,
        play,
        status_snapshot,
        stop,
        wait_for_pie,
    )
except ImportError:
    from hephaestus_forge.pie_control import (  # type: ignore
        editor_online,
        pie_online,
        play,
        status_snapshot,
        stop,
        wait_for_pie,
    )

try:
    from preflight_health import pie_matches_project
except ImportError:
    from hephaestus_forge.preflight_health import pie_matches_project  # type: ignore


def find_ue_root() -> Optional[Path]:
    """Locate UE 5.8 engine root (UE_PATH or common install dirs)."""

    def _ok(path: Path) -> bool:
        if not path.is_dir():
            return False
        editor = path / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
        if not editor.is_file() and sys.platform != "win32":
            # Non-Windows: accept Engine/Binaries presence.
            return (path / "Engine" / "Binaries").is_dir()
        return editor.is_file() if sys.platform == "win32" else (path / "Engine").is_dir()

    env = os.environ.get("UE_PATH", "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if _ok(root):
            return root

    candidates = [
        Path.home() / "UnrealEngine" / "5.8",
        Path("C:/UnrealEngine/5.8"),
        Path("D:/UnrealEngine/5.8"),
        Path("C:/Program Files/Epic Games/UE_5.8"),
        Path("/opt/UnrealEngine/5.8"),
    ]
    for path in candidates:
        if _ok(path):
            return path.resolve()
    return None


def unreal_editor_exe(ue_root: Optional[Path] = None) -> Path:
    root = ue_root or find_ue_root()
    if root is None:
        raise FileNotFoundError(
            "UE 5.8 not found — set UE_PATH to the engine root "
            "(e.g. C:\\Program Files\\Epic Games\\UE_5.8)"
        )
    if sys.platform == "win32":
        exe = root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
    elif sys.platform == "darwin":
        exe = root / "Engine" / "Binaries" / "Mac" / "UnrealEditor"
    else:
        exe = root / "Engine" / "Binaries" / "Linux" / "UnrealEditor"
    if not exe.is_file():
        raise FileNotFoundError(f"UnrealEditor not found at {exe}")
    return exe


def resolve_uproject(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if root.suffix.lower() == ".uproject" and root.is_file():
        return root
    projects = sorted(root.glob("*.uproject"))
    if not projects:
        raise FileNotFoundError(f"No .uproject under {root}")
    return projects[0]


def editor_matches_project(health: dict[str, Any], project_root: Path) -> tuple[bool, str]:
    """Reuse PIE identity rules against editor health payload."""
    return pie_matches_project(health, Path(project_root))


def wait_for_editor(
    project_root: Optional[Path] = None,
    *,
    timeout_s: float = 180.0,
    poll_s: float = 2.0,
) -> tuple[bool, dict[str, Any], str]:
    """Poll editor :8766 until healthy (and identity matches when project_root given)."""
    deadline = time.time() + timeout_s
    last_detail = "waiting for editor API :8766"
    last_health: dict[str, Any] = {}
    while time.time() < deadline:
        ok, health, detail = editor_online(timeout=2.0)
        last_health = health
        if not ok:
            last_detail = detail
            time.sleep(poll_s)
            continue
        if project_root is not None:
            match_ok, match_detail = editor_matches_project(health, Path(project_root))
            if not match_ok:
                last_detail = match_detail
                time.sleep(poll_s)
                continue
            return True, health, match_detail
        return True, health, detail
    return False, last_health, last_detail


def open_editor(
    project_root: Path,
    *,
    ue_root: Optional[Path] = None,
    extra_args: Optional[list[str]] = None,
    wait_timeout_s: float = 180.0,
) -> dict[str, Any]:
    """
    Ensure Unreal Editor is open on project_root.

    If editor API already matches this project, no-op.
    If editor is open on a different project, raise.
    Otherwise launch UnrealEditor.exe with the .uproject and wait for :8766.
    """
    root = Path(project_root).expanduser().resolve()
    uproject = resolve_uproject(root)
    project_dir = uproject.parent

    ed_ok, ed_health, ed_detail = editor_online()
    if ed_ok:
        match_ok, match_detail = editor_matches_project(ed_health, project_dir)
        if match_ok:
            return {
                "ok": True,
                "launched": False,
                "detail": match_detail,
                "health": ed_health,
                "uproject": str(uproject),
            }
        raise RuntimeError(
            f"Editor already open on a different project ({match_detail}). "
            f"Close Unreal or run forge down --quit-editor, then retry."
        )

    editor = unreal_editor_exe(ue_root)
    cmd = [str(editor), str(uproject)]
    if extra_args:
        cmd.extend(extra_args)
    # Keep session lightweight for agent use; operator can override via env later.
    proc = subprocess.Popen(
        cmd,
        cwd=str(project_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ok, health, detail = wait_for_editor(project_dir, timeout_s=wait_timeout_s)
    if not ok:
        # Leave the process running — editor may still be loading assets.
        return {
            "ok": False,
            "launched": True,
            "pid": proc.pid,
            "detail": detail,
            "health": health,
            "uproject": str(uproject),
            "error": (
                f"Launched UnrealEditor (pid {proc.pid}) but editor API :8766 "
                f"did not become ready in {wait_timeout_s}s — "
                f"ensure HephaestusBridge ≥1.0.1 is rebuilt. ({detail})"
            ),
        }
    return {
        "ok": True,
        "launched": True,
        "pid": proc.pid,
        "detail": detail,
        "health": health,
        "uproject": str(uproject),
    }


def quit_editor(*, force: bool = True) -> dict[str, Any]:
    """Stop UnrealEditor processes (Windows-focused; best-effort elsewhere)."""
    killed: list[str] = []
    if sys.platform == "win32":
        for name in ("UnrealEditor.exe", "UnrealEditor-Win64-DebugGame.exe"):
            try:
                flags = ["/IM", name, "/T"]
                if force:
                    flags.insert(0, "/F")
                r = subprocess.run(
                    ["taskkill", *flags],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if r.returncode == 0 or "SUCCESS" in (r.stdout or "").upper():
                    killed.append(name)
            except Exception:
                continue
    else:
        try:
            subprocess.run(["pkill", "-f", "UnrealEditor"], check=False, timeout=15)
            killed.append("UnrealEditor")
        except Exception:
            pass

    # Wait briefly for :8766 to drop
    deadline = time.time() + 20.0
    while time.time() < deadline:
        ok, _, _ = editor_online(timeout=1.0)
        if not ok:
            break
        time.sleep(1.0)

    still_up, _, detail = editor_online(timeout=1.0)
    return {
        "ok": not still_up,
        "killed": killed,
        "editor_still_online": still_up,
        "detail": "editor offline" if not still_up else detail,
    }


def bring_up(
    project_root: Path,
    *,
    pie_timeout_s: float = 60.0,
    editor_timeout_s: float = 180.0,
    open_if_needed: bool = True,
    start_dcc: bool = True,
) -> dict[str, Any]:
    """Open editor if needed, wait :8766, start PIE, optionally start DCC :8084."""
    root = Path(project_root).expanduser().resolve()
    uproject = resolve_uproject(root)
    project_dir = uproject.parent

    dcc_info: dict[str, Any] = {"ok": False, "skipped": not start_dcc}
    if start_dcc:
        try:
            from dcc_client import start_dcc_server, dcc_online
        except ImportError:
            try:
                from hephaestus_forge.dcc_client import start_dcc_server, dcc_online  # type: ignore
            except ImportError:
                start_dcc_server = None  # type: ignore
                dcc_online = None  # type: ignore
        if start_dcc_server:
            try:
                dcc_info = start_dcc_server()
            except Exception as exc:
                dcc_info = {"ok": False, "error": str(exc), "detail": "DCC start failed (non-blocking)"}
        elif dcc_online:
            ok, _, detail = dcc_online()
            dcc_info = {"ok": ok, "detail": detail}

    launch: dict[str, Any] = {"ok": True, "launched": False, "detail": "editor already ready"}
    ed_ok, ed_health, ed_detail = editor_online()
    if ed_ok:
        match_ok, match_detail = editor_matches_project(ed_health, project_dir)
        if not match_ok:
            return {
                "ok": False,
                "error": (
                    f"Editor open on wrong project ({match_detail}). "
                    f"forge down --quit-editor then forge up again."
                ),
                "editor": ed_health,
                "dcc": dcc_info,
            }
    elif open_if_needed:
        launch = open_editor(project_dir, wait_timeout_s=editor_timeout_s)
        if not launch.get("ok"):
            return {"ok": False, "phase": "editor_open", "dcc": dcc_info, **launch}
    else:
        return {
            "ok": False,
            "error": f"Editor offline ({ed_detail}). Pass open_if_needed or run forge editor open.",
            "dcc": dcc_info,
        }

    # Ensure editor still matches after launch wait
    ed_ok, ed_health, ed_detail = editor_online()
    if not ed_ok:
        return {"ok": False, "phase": "editor_wait", "error": ed_detail, "launch": launch, "dcc": dcc_info}

    pie_ok, _, _ = pie_online()
    if pie_ok:
        snap = status_snapshot(project_dir)
        if snap.get("pie_online"):
            return {
                "ok": True,
                "already_pie": True,
                "detail": snap.get("pie_detail") or snap.get("identity") or "PIE already online",
                "launch": launch,
                "status": snap,
                "dcc": dcc_info,
            }

    play_result = play()
    if not play_result.get("success"):
        return {
            "ok": False,
            "phase": "pie_play",
            "error": play_result.get("error") or "editor.play failed",
            "play": play_result,
            "launch": launch,
            "dcc": dcc_info,
        }

    ok, health, detail = wait_for_pie(project_dir, timeout_s=pie_timeout_s)
    return {
        "ok": ok,
        "already_pie": False,
        "detail": detail,
        "play": play_result,
        "health": health,
        "launch": launch,
        "dcc": dcc_info,
        "error": None if ok else detail,
    }


def bring_down(*, quit_editor_flag: bool = False) -> dict[str, Any]:
    """Stop PIE; optionally quit Unreal Editor."""
    stop_result: dict[str, Any] = {"success": True, "skipped": True}
    ed_ok, _, _ = editor_online()
    pie_ok, _, _ = pie_online()
    if ed_ok or pie_ok:
        try:
            stop_result = stop()
        except Exception as exc:
            stop_result = {"success": False, "error": str(exc)}

    quit_result = None
    if quit_editor_flag:
        # Give PIE a moment to tear down before killing the editor process.
        time.sleep(1.5)
        quit_result = quit_editor()

    ok = bool(stop_result.get("success", True)) and (
        quit_result is None or quit_result.get("ok")
    )
    return {
        "ok": ok,
        "stop": stop_result,
        "quit_editor": quit_result,
    }
