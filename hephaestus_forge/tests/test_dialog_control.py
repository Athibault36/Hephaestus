# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for dialog_control (no live Windows UI required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dialog_control as dc  # noqa: E402


def test_normalize_and_match_button():
    buttons = ["Don't Restore", "Restore", "Cancel"]
    assert dc._match_button(buttons, "don't restore") == "Don't Restore"
    assert dc._match_button(buttons, "Cancel") == "Cancel"
    assert dc._match_button(buttons, "nope") is None


def test_match_action_cancel_prefers_dont_restore_when_listed():
    # Semantic cancel list includes Don't Restore via ACTION_BUTTONS["cancel"]
    buttons = ["Restore", "Don't Restore", "Cancel"]
    # cancel action prefers Cancel before Don't Restore in ACTION_BUTTONS order...
    # Actually cancel tuple is Cancel, No, Close, Don't Restore — Cancel wins.
    assert dc._match_action(buttons, "cancel") == "Cancel"
    assert dc._match_action(["Don't Restore", "Restore"], "cancel") == "Don't Restore"
    assert dc._match_action(["Yes", "No"], "yes") == "Yes"
    assert dc._match_action(["OK"], "accept") == "OK"


def test_known_match_restore_packages():
    spec = dc._known_match("Restore Packages", "UnrealEditor.exe")
    assert spec is not None
    assert spec["id"] == "ue_restore_packages"
    assert "Don't Restore" in spec["buttons"]


def test_known_match_requires_process_when_set():
    # Title matches but wrong process → still match if process empty is ok;
    # with process_re set, non-matching process should fail
    spec = dc._known_match("Restore Packages", "notepad.exe")
    assert spec is None


def test_known_match_message_log_closes():
    spec = dc._known_match("Message Log", "UnrealEditor.exe")
    assert spec is not None
    assert spec["id"] == "ue_message_log"
    assert spec.get("close") is True


def test_auto_dismiss_closes_message_log(monkeypatch):
    dialogs = [
        {
            "hwnd": 99,
            "title": "Message Log",
            "process_name": "UnrealEditor.exe",
            "buttons": [],
            "known_id": "ue_message_log",
            "class_name": "UnrealWindow",
            "pid": 1,
        }
    ]
    monkeypatch.setattr(
        dc,
        "list_dialogs",
        lambda include_main_windows=False: {
            "ok": True,
            "backend": "test",
            "dialogs": dialogs,
            "count": 1,
        },
    )
    monkeypatch.setattr(dc, "_close_window", lambda hwnd: {"ok": True, "clicked": "WM_CLOSE", "method": "test"})
    res = dc.auto_dismiss(only_known=True, target_processes_only=True)
    assert res["handled_count"] == 1
    assert res["handled"][0]["result"]["clicked"] == "WM_CLOSE"


def test_click_dialog_resolves_action(monkeypatch):
    monkeypatch.setattr(
        dc,
        "list_dialogs",
        lambda include_main_windows=False: {
            "ok": True,
            "backend": "test",
            "dialogs": [
                {
                    "hwnd": 7,
                    "title": "Confirm",
                    "buttons": ["Yes", "No"],
                    "process_name": "UnrealEditor.exe",
                    "class_name": "#32770",
                    "pid": 1,
                    "known_id": "",
                }
            ],
            "count": 1,
        },
    )
    monkeypatch.setattr(dc, "_backend_available", lambda: (True, "test"))
    monkeypatch.setattr(
        dc,
        "_click_button_pywinauto",
        lambda hwnd, button_text: {"ok": True, "clicked": button_text, "method": "test"},
    )
    monkeypatch.setattr(
        dc,
        "_click_button_win32",
        lambda hwnd, button_text: {"ok": True, "clicked": button_text, "method": "test"},
    )
    # Force win32 path by making backend win32
    monkeypatch.setattr(dc, "_backend_available", lambda: (True, "win32"))
    res = dc.click_dialog(title="Confirm", action="yes")
    assert res["ok"] is True
    assert res["clicked"] == "Yes"
