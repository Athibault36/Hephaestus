# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Windows dialog / MessageBox control for Hephaestus automation.

Lets forge, Mission Control, and agents list open modal dialogs and click
Accept / Cancel / Yes / No / custom buttons — including known Unreal blockers
like \"Restore Packages\".
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Preferred button labels for semantic actions (first match wins).
ACTION_BUTTONS: dict[str, tuple[str, ...]] = {
    "accept": (
        "OK",
        "&OK",
        "Yes",
        "&Yes",
        "Accept",
        "Continue",
        "Allow",
        "Retry",
        "Open",
        "Save",
        "Apply",
        "Import",
        "Export",
        "Overwrite",
        "Replace",
        "Update",
        "Ignore",
        "Skip",
        "Proceed",
        "I Agree",
        "Agree",
        "Finish",
        "Close",
    ),
    "ok": ("OK", "&OK", "Close"),
    "yes": ("Yes", "&Yes", "OK", "&OK"),
    "cancel": (
        "Cancel",
        "&Cancel",
        "No",
        "&No",
        "Close",
        "Don't Restore",
        "Don't Save",
        "Discard",
        "Abort",
        "Ignore",
    ),
    "no": ("No", "&No", "Cancel", "&Cancel"),
    "dismiss": (
        "Cancel",
        "&Cancel",
        "No",
        "&No",
        "Close",
        "Don't Restore",
        "Don't Save",
        "Discard",
        "OK",
        "Ignore",
        "Skip",
    ),
}

# Processes Hephaestus is allowed to dismiss dialogs for (never touch Cursor/browsers).
TARGET_PROCESSES: tuple[str, ...] = (
    "UnrealEditor",
    "UE4Editor",
    "CrashReportClient",
    "CharacterCreator",
)

# Known Hephaestus / UE / CC5 dialogs and the preferred click (in order).
KNOWN_DIALOGS: tuple[dict[str, Any], ...] = (
    {
        "id": "ue_restore_packages",
        "title_re": r"Restore Packages",
        "process_re": r"UnrealEditor",
        "buttons": ("Don't Restore", "Don't Save", "No", "Cancel"),
        "reason": "UE restore-packages prompt blocks editor startup",
    },
    {
        "id": "ue_live_coding",
        "title_re": r"Live Coding|Live Coding Console",
        "process_re": r"UnrealEditor",
        "buttons": ("Cancel", "Close", "OK", "Abort"),
        "reason": "Live Coding modal can block plugin rebuilds",
    },
    {
        "id": "ue_message",
        "title_re": r"^Message$",
        "process_re": r"UnrealEditor",
        "buttons": ("OK", "Yes", "Cancel", "No"),
        "reason": "Generic Unreal MessageBox",
    },
    {
        "id": "ue_message_log",
        "title_re": r"^Message Log$",
        "process_re": r"UnrealEditor",
        "buttons": (),
        "close": True,
        "reason": "Message Log panel steals focus during automation",
    },
    {
        "id": "ue_output_log",
        "title_re": r"^Output Log$",
        "process_re": r"UnrealEditor",
        "buttons": (),
        "close": True,
        "reason": "Output Log floating window",
    },
    {
        "id": "ue_fbx_import",
        "title_re": r"FBX Import|Import Options|Import Content|Import Summary",
        "process_re": r"UnrealEditor",
        "buttons": ("Import", "OK", "Yes", "Continue", "Close"),
        "reason": "FBX import options block editor.import_fbx",
    },
    {
        "id": "ue_overwrite",
        "title_re": r"Overwrite|Already Exists|Replace|Save Package",
        "process_re": r"UnrealEditor",
        "buttons": ("Yes", "Overwrite", "Replace", "OK", "Continue"),
        "reason": "Overwrite prompts during asset import",
    },
    {
        "id": "ue_crash_report",
        "title_re": r"Crash Report|Send Unattended|Unreal Engine.*Crash",
        "process_re": r"UnrealEditor|CrashReportClient",
        "buttons": ("Close", "Cancel", "Don't Send", "No", "OK"),
        "reason": "Crash reporter blocks automation",
    },
    {
        "id": "ue_shader",
        "title_re": r"Shader Compile|Compiling Shaders|Global Shaders",
        "process_re": r"UnrealEditor",
        "buttons": ("OK", "Close", "Cancel"),
        "reason": "Shader compile dialog",
    },
    {
        "id": "ue_slow_task",
        "title_re": r"Slow Task|Please Wait|Progress",
        "process_re": r"UnrealEditor",
        "buttons": ("Cancel", "Close"),
        "reason": "Slow task dialog — cancel only if stuck",
        "skip_auto": True,
    },
    {
        "id": "ue_datasmith",
        "title_re": r"Datasmith|Interchange",
        "process_re": r"UnrealEditor",
        "buttons": ("OK", "Import", "Yes", "Continue", "Close"),
        "reason": "Interchange/Datasmith import prompts",
    },
    {
        "id": "ue_missing_asset",
        "title_re": r"Missing|Failed to Load|Warning|Error",
        "process_re": r"UnrealEditor",
        "buttons": ("OK", "Yes", "Continue", "Ignore", "Close", "Cancel"),
        "reason": "Missing asset / warning MessageBox",
    },
    {
        "id": "windows_uac_style_save",
        "title_re": r"Save.*\?|Save Changes|Save Level",
        "process_re": r"UnrealEditor|CharacterCreator",
        "buttons": ("Don't Save", "No", "Cancel"),
        "reason": "Save-prompt during quit/restart",
    },
    {
        "id": "cc5_export",
        "title_re": r"Export FBX|FBX Export|Export Options|Exporting|Overwrite File|File Exists",
        "process_re": r"CharacterCreator",
        "buttons": ("OK", "Yes", "Export", "Continue", "Overwrite", "Replace", "Close"),
        "reason": "CC5 export / overwrite prompts",
    },
    {
        "id": "cc5_message",
        "title_re": r"^Message$|^Warning$|^Error$|^Confirm$|^Information$",
        "process_re": r"CharacterCreator",
        "buttons": ("OK", "Yes", "Continue", "Close", "Cancel"),
        "reason": "CC5 MessageBox",
    },
    {
        "id": "reallusion_hub",
        "title_re": r"Update Available|Download Update|^Reallusion Hub$",
        "process_re": r"Reallusion",
        "buttons": ("Cancel", "Close", "No", "Later", "OK"),
        "close": True,
        "reason": "Hub window / update prompts distract automation",
    },
)


@dataclass
class DialogInfo:
    hwnd: int
    title: str
    class_name: str = ""
    process_name: str = ""
    pid: int = 0
    buttons: list[str] = field(default_factory=list)
    known_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _backend_available() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "dialog control requires Windows"
    try:
        import pywinauto  # noqa: F401

        return True, "pywinauto"
    except ImportError:
        pass
    try:
        import win32gui  # noqa: F401

        return True, "win32"
    except ImportError:
        return False, "install pywinauto or pywin32"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("&", "").strip()).lower()


def _match_button(available: list[str], wanted: str) -> Optional[str]:
    want = _normalize(wanted)
    if not want:
        return None
    for b in available:
        if _normalize(b) == want:
            return b
    for b in available:
        if want in _normalize(b) or _normalize(b) in want:
            return b
    return None


def _match_action(available: list[str], action: str) -> Optional[str]:
    labels = ACTION_BUTTONS.get(action.strip().lower(), ())
    for label in labels:
        hit = _match_button(available, label)
        if hit:
            return hit
    return None


def _known_match(title: str, process_name: str) -> Optional[dict[str, Any]]:
    for spec in KNOWN_DIALOGS:
        if not re.search(spec["title_re"], title or "", re.I):
            continue
        pre = spec.get("process_re")
        if pre and process_name and not re.search(str(pre), process_name, re.I):
            continue
        return spec
    return None


def _list_via_pywinauto() -> list[DialogInfo]:
    from pywinauto import Desktop

    desk = Desktop(backend="win32")
    out: list[DialogInfo] = []
    for w in desk.windows():
        try:
            if not w.is_visible():
                continue
            title = (w.window_text() or "").strip()
            if not title:
                continue
            class_name = ""
            try:
                class_name = w.class_name() or ""
            except Exception:
                pass
            # Prefer modal-ish / dialog classes, but keep titled top-levels that look like prompts
            is_dialogish = (
                "dialog" in class_name.lower()
                or class_name in ("#32770",)
                or bool(_known_match(title, ""))
                or any(
                    k in title.lower()
                    for k in ("restore", "save", "crash", "error", "warning", "confirm", "message")
                )
            )
            if not is_dialogish and class_name not in ("#32770",):
                # Still include small top-level windows with few controls that look like MessageBoxes
                try:
                    rect = w.rectangle()
                    if (rect.width() > 900 and rect.height() > 700) and "Unreal" in title:
                        continue  # main editor frame
                except Exception:
                    pass
            pid = 0
            process_name = ""
            try:
                pid = int(w.process_id())
                import psutil  # optional

                process_name = psutil.Process(pid).name()
            except Exception:
                try:
                    import win32process
                    import win32api

                    pid = int(w.process_id())
                    handle = win32api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                    try:
                        process_name = win32process.GetModuleFileNameEx(handle, 0)
                        process_name = process_name.split("\\")[-1]
                    finally:
                        win32api.CloseHandle(handle)
                except Exception:
                    process_name = ""

            buttons: list[str] = []
            try:
                for ctrl in w.descendants():
                    try:
                        cname = (ctrl.class_name() or "").lower()
                        if "button" not in cname:
                            continue
                        text = (ctrl.window_text() or "").strip()
                        if text and text not in buttons:
                            buttons.append(text)
                    except Exception:
                        continue
            except Exception:
                pass

            known = _known_match(title, process_name) or {}
            out.append(
                DialogInfo(
                    hwnd=int(w.handle),
                    title=title,
                    class_name=class_name,
                    process_name=process_name,
                    pid=pid,
                    buttons=buttons,
                    known_id=str(known.get("id") or ""),
                )
            )
        except Exception:
            continue
    return out


def _list_via_win32() -> list[DialogInfo]:
    import win32gui
    import win32process

    out: list[DialogInfo] = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        if not title:
            return True
        class_name = win32gui.GetClassName(hwnd) or ""
        if class_name != "#32770" and not _known_match(title, ""):
            return True
        pid = 0
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pass
        buttons: list[str] = []

        def _child(ch, __):
            try:
                if (win32gui.GetClassName(ch) or "").lower().find("button") >= 0:
                    t = (win32gui.GetWindowText(ch) or "").strip()
                    if t and t not in buttons:
                        buttons.append(t)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumChildWindows(hwnd, _child, None)
        except Exception:
            pass
        known = _known_match(title, "") or {}
        out.append(
            DialogInfo(
                hwnd=int(hwnd),
                title=title,
                class_name=class_name,
                pid=int(pid or 0),
                buttons=buttons,
                known_id=str(known.get("id") or ""),
            )
        )
        return True

    win32gui.EnumWindows(_enum, None)
    return out


def list_dialogs(*, include_main_windows: bool = False) -> dict[str, Any]:
    """List visible dialog-like windows (and their buttons when discoverable)."""
    ok, backend = _backend_available()
    if not ok:
        return {"ok": False, "error": backend, "dialogs": []}
    try:
        if backend == "pywinauto":
            dialogs = _list_via_pywinauto()
        else:
            dialogs = _list_via_win32()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "dialogs": [], "backend": backend}

    if not include_main_windows:
        filtered: list[DialogInfo] = []
        for d in dialogs:
            if d.known_id or d.class_name == "#32770" or d.buttons:
                filtered.append(d)
            elif any(
                k in d.title.lower()
                for k in ("restore", "save", "crash", "error", "warning", "confirm", "message")
            ):
                filtered.append(d)
        dialogs = filtered

    return {
        "ok": True,
        "backend": backend,
        "count": len(dialogs),
        "dialogs": [d.to_dict() for d in dialogs],
    }


def _click_button_pywinauto(hwnd: int, button_text: str) -> dict[str, Any]:
    # Prefer win32 BM_CLICK first — click_input fails across integrity levels
    # when Unreal was started elevated and forge was not (UIPI).
    win32_res = _click_button_win32(hwnd, button_text)
    if win32_res.get("ok"):
        win32_res["method"] = "BM_CLICK_first"
        return win32_res
    # Avoid click_input when UIPI blocks — it hangs with Admin warnings.
    err = str(win32_res.get("error") or "")
    if "not found" not in err.lower():
        return {
            "ok": False,
            "error": f"win32 click failed (skipping click_input to avoid UIPI hang): {err}",
            "wanted": button_text,
        }
    from pywinauto import Application

    app = Application(backend="win32").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    try:
        # .click() uses messages; less likely to hang than click_input()
        win.child_window(title=button_text, class_name="Button").click()
        return {"ok": True, "clicked": button_text, "method": "title_click"}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"button not clickable: {exc}; win32={err}",
            "wanted": button_text,
        }


def _click_button_win32(hwnd: int, button_text: str) -> dict[str, Any]:
    import win32gui
    import win32con

    target: list[int] = []

    def _child(ch, __):
        try:
            if "button" not in (win32gui.GetClassName(ch) or "").lower():
                return True
            t = (win32gui.GetWindowText(ch) or "").strip()
            if _normalize(t) == _normalize(button_text) or _normalize(button_text) in _normalize(t):
                target.append(ch)
                return False
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(hwnd, _child, None)
    if not target:
        return {"ok": False, "error": f"button not found: {button_text}", "wanted": button_text}
    btn = target[0]
    win32gui.SetForegroundWindow(hwnd)
    win32gui.SendMessage(btn, win32con.BM_CLICK, 0, 0)
    return {"ok": True, "clicked": button_text, "method": "BM_CLICK", "hwnd": int(btn)}


def click_dialog(
    *,
    title: Optional[str] = None,
    title_re: Optional[str] = None,
    hwnd: Optional[int] = None,
    button: Optional[str] = None,
    action: Optional[str] = None,
) -> dict[str, Any]:
    """
    Click a button on a dialog.

    Provide hwnd, or title / title_re to find it. Then either ``button`` text
    or semantic ``action`` (accept|cancel|yes|no|ok|dismiss).
    """
    ok, backend = _backend_available()
    if not ok:
        return {"ok": False, "error": backend}

    listing = list_dialogs(include_main_windows=True)
    if not listing.get("ok"):
        return listing
    dialogs = listing.get("dialogs") or []

    chosen: Optional[dict[str, Any]] = None
    if hwnd is not None:
        for d in dialogs:
            if int(d.get("hwnd") or 0) == int(hwnd):
                chosen = d
                break
        if chosen is None:
            chosen = {"hwnd": int(hwnd), "title": title or "", "buttons": []}
    else:
        for d in dialogs:
            t = d.get("title") or ""
            if title and _normalize(title) in _normalize(t):
                chosen = d
                break
            if title_re and re.search(title_re, t, re.I):
                chosen = d
                break
        if chosen is None and title:
            # Retry raw connect by title via pywinauto even if filtered out
            if backend == "pywinauto":
                try:
                    from pywinauto import Desktop

                    w = Desktop(backend="win32").window(title_re=f".*{re.escape(title)}.*")
                    if w.exists():
                        chosen = {
                            "hwnd": int(w.handle),
                            "title": w.window_text(),
                            "buttons": [],
                        }
                except Exception:
                    pass

    if chosen is None:
        return {
            "ok": False,
            "error": "dialog not found",
            "title": title,
            "title_re": title_re,
            "available": [{"title": d.get("title"), "hwnd": d.get("hwnd")} for d in dialogs[:20]],
        }

    buttons = list(chosen.get("buttons") or [])
    click_label: Optional[str] = None
    if button:
        click_label = _match_button(buttons, button) if buttons else button
        if click_label is None:
            click_label = button
    elif action:
        click_label = _match_action(buttons, action) if buttons else None
        if click_label is None:
            # Try action defaults even without enumerated buttons
            for label in ACTION_BUTTONS.get(action.strip().lower(), ()):
                click_label = label.replace("&", "")
                break
    else:
        return {"ok": False, "error": "provide button= or action= (accept|cancel|yes|no|ok|dismiss)"}

    assert click_label is not None
    handle = int(chosen["hwnd"])
    # Always try win32 BM_CLICK first (works when click_input is blocked by UIPI).
    result = _click_button_win32(handle, click_label)
    if not result.get("ok") and backend == "pywinauto":
        result = _click_button_pywinauto(handle, click_label)
    elif not result.get("ok"):
        result = _click_button_win32(handle, click_label)

    result.update(
        {
            "dialog_title": chosen.get("title"),
            "dialog_hwnd": handle,
            "action": action,
            "button_requested": button,
            "backend": backend,
        }
    )
    return result


def _target_process(process_name: str) -> bool:
    pn = (process_name or "").lower()
    if not pn:
        return False
    return any(t.lower() in pn for t in TARGET_PROCESSES)


def _close_window(hwnd: int) -> dict[str, Any]:
    """WM_CLOSE for panels like Message Log that have no buttons."""
    try:
        import win32con
        import win32gui

        win32gui.PostMessage(int(hwnd), win32con.WM_CLOSE, 0, 0)
        return {"ok": True, "clicked": "WM_CLOSE", "method": "close"}
    except Exception as exc:
        try:
            from pywinauto import Application

            app = Application(backend="win32").connect(handle=int(hwnd))
            app.window(handle=int(hwnd)).close()
            return {"ok": True, "clicked": "close", "method": "pywinauto_close"}
        except Exception as exc2:
            return {"ok": False, "error": f"close failed: {exc}; {exc2}"}


def auto_dismiss(*, only_known: bool = True, target_processes_only: bool = True) -> dict[str, Any]:
    """
    Dismiss Hephaestus-relevant dialogs.

    - Known UE/CC5 dialogs (Restore Packages, FBX Import, Message Log, …)
    - Any #32770 modal from UnrealEditor / CharacterCreator when only_known=False
      or when it has standard OK/Yes/Import buttons (process-scoped safe auto)
    Never touches Cursor, browsers, or unrelated apps.
    """
    listing = list_dialogs(include_main_windows=False)
    if not listing.get("ok"):
        # Fallback: include dialogish titles from target processes
        listing = list_dialogs(include_main_windows=True)
        if not listing.get("ok"):
            return listing

    handled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for d in listing.get("dialogs") or []:
        title = d.get("title") or ""
        process = d.get("process_name") or ""
        class_name = d.get("class_name") or ""
        if target_processes_only and process and not _target_process(process):
            continue
        if target_processes_only and not process:
            # Keep known titles even without process attribution
            if not _known_match(title, "UnrealEditor.exe"):
                continue

        spec = _known_match(title, process or "UnrealEditor.exe")
        if spec and spec.get("skip_auto"):
            skipped.append({"title": title, "hwnd": d.get("hwnd"), "reason": "skip_auto"})
            continue

        # Process-scoped: treat UE/CC5 #32770 modals as dismissible even if not named
        is_target_modal = _target_process(process) and (
            class_name == "#32770"
            or bool(d.get("buttons"))
            or bool(spec)
            or any(
                k in title.lower()
                for k in (
                    "restore",
                    "save",
                    "crash",
                    "error",
                    "warning",
                    "confirm",
                    "message",
                    "import",
                    "export",
                    "overwrite",
                    "fbx",
                    "plugin",
                )
            )
        )

        if only_known and not spec and not is_target_modal:
            skipped.append({"title": title, "hwnd": d.get("hwnd"), "reason": "not_known"})
            continue
        if not only_known and target_processes_only and not is_target_modal and not spec:
            skipped.append({"title": title, "hwnd": d.get("hwnd"), "reason": "not_target_modal"})
            continue

        if spec and spec.get("close"):
            res = _close_window(int(d["hwnd"]))
            if res.get("ok"):
                handled.append(
                    {
                        "known_id": spec.get("id"),
                        "title": title,
                        "result": res,
                        "reason": spec.get("reason"),
                    }
                )
                continue
            # fall through to button clicks if close failed

        buttons_pref: tuple[str, ...]
        if spec and spec.get("buttons"):
            buttons_pref = tuple(spec.get("buttons") or ())
        elif is_target_modal:
            # Prefer accept/import for automation blockers; cancel for save prompts
            if any(k in title.lower() for k in ("save", "restore")):
                buttons_pref = ACTION_BUTTONS["dismiss"]
            else:
                buttons_pref = ACTION_BUTTONS["accept"] + ACTION_BUTTONS["dismiss"]
        else:
            buttons_pref = ACTION_BUTTONS["dismiss"]

        available = list(d.get("buttons") or [])
        clicked = None
        last_err = None
        for pref in buttons_pref:
            label = _match_button(available, pref) if available else pref
            if not label:
                continue
            res = click_dialog(hwnd=int(d["hwnd"]), button=label)
            if res.get("ok"):
                clicked = res
                break
            last_err = res
        if clicked is None and not available:
            # No enumerated buttons — try OK then close
            for label in ("OK", "Yes", "Close", "Cancel"):
                res = click_dialog(hwnd=int(d["hwnd"]), button=label)
                if res.get("ok"):
                    clicked = res
                    break
                last_err = res
            if clicked is None:
                res = _close_window(int(d["hwnd"]))
                if res.get("ok"):
                    clicked = res
                else:
                    last_err = res
        if clicked:
            handled.append(
                {
                    "known_id": (spec or {}).get("id"),
                    "title": title,
                    "result": clicked,
                    "reason": (spec or {}).get("reason") or "target_modal",
                }
            )
        else:
            skipped.append(
                {
                    "title": title,
                    "hwnd": d.get("hwnd"),
                    "reason": "click_failed",
                    "error": (last_err or {}).get("error"),
                    "buttons": available,
                }
            )

    return {
        "ok": True,
        "handled": handled,
        "skipped": skipped,
        "handled_count": len(handled),
        "backend": listing.get("backend"),
    }


def watch_and_dismiss(
    *,
    duration_s: float = 60.0,
    interval_s: float = 1.5,
    only_known: bool = False,
) -> dict[str, Any]:
    """Poll for dialogs and auto-dismiss until duration expires."""
    deadline = time.time() + max(0.0, duration_s)
    events: list[dict[str, Any]] = []
    while time.time() < deadline:
        res = auto_dismiss(only_known=only_known, target_processes_only=True)
        if res.get("handled_count"):
            events.append({"t": time.time(), **{k: res[k] for k in ("handled_count", "handled")}})
        time.sleep(max(0.2, interval_s))
    return {
        "ok": True,
        "events": events,
        "dismissed_total": sum(int(e.get("handled_count") or 0) for e in events),
        "duration_s": duration_s,
    }


def dismiss_while(
    predicate,
    *,
    timeout_s: float = 180.0,
    poll_s: float = 2.0,
    only_known: bool = True,
) -> dict[str, Any]:
    """
    Run ``predicate() -> bool`` until True or timeout, dismissing dialogs each poll.

    Used by editor launch waits so Restore Packages cannot block :8766 forever.
    """
    deadline = time.time() + timeout_s
    dismissed: list[dict[str, Any]] = []
    last_pred = False
    while time.time() < deadline:
        try:
            last_pred = bool(predicate())
        except Exception:
            last_pred = False
        if last_pred:
            return {"ok": True, "ready": True, "dismissed": dismissed}
        res = auto_dismiss(only_known=False, target_processes_only=True)
        if res.get("handled_count"):
            dismissed.extend(res.get("handled") or [])
        time.sleep(poll_s)
    return {"ok": False, "ready": False, "dismissed": dismissed, "error": "timeout"}
