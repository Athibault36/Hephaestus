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
    "accept": ("OK", "&OK", "Yes", "&Yes", "Accept", "Continue", "Allow", "Retry", "Open", "Save", "Apply"),
    "ok": ("OK", "&OK"),
    "yes": ("Yes", "&Yes", "OK", "&OK"),
    "cancel": ("Cancel", "&Cancel", "No", "&No", "Close", "Don't Restore", "Don't Save", "Discard"),
    "no": ("No", "&No", "Cancel", "&Cancel"),
    "dismiss": ("Cancel", "&Cancel", "No", "&No", "Close", "Don't Restore", "Don't Save", "OK"),
}

# Known Hephaestus / UE dialogs and the preferred click (in order).
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
        "id": "ue_crash_report",
        "title_re": r"Crash Report|Send Unattended|Unreal Engine.*Crash",
        "process_re": r"UnrealEditor|CrashReportClient",
        "buttons": ("Close", "Cancel", "Don't Send", "No", "OK"),
        "reason": "Crash reporter blocks automation",
    },
    {
        "id": "windows_uac_style_save",
        "title_re": r"Save.*\?|Save Changes",
        "process_re": r"UnrealEditor|CharacterCreator",
        "buttons": ("Don't Save", "No", "Cancel"),
        "reason": "Save-prompt during quit/restart",
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
    from pywinauto import Application

    app = Application(backend="win32").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    win.set_focus()
    # Exact then fuzzy
    try:
        win.child_window(title=button_text, class_name="Button").click_input()
        return {"ok": True, "clicked": button_text, "method": "title"}
    except Exception:
        pass
    try:
        win.child_window(title_re=f".*{re.escape(button_text)}.*", class_name="Button").click_input()
        return {"ok": True, "clicked": button_text, "method": "title_re"}
    except Exception as exc:
        # Fallback: enumerate
        for ctrl in win.descendants(class_name="Button"):
            try:
                text = (ctrl.window_text() or "").strip()
                if _normalize(text) == _normalize(button_text) or _normalize(button_text) in _normalize(text):
                    ctrl.click_input()
                    return {"ok": True, "clicked": text, "method": "enumerate"}
            except Exception:
                continue
        return {"ok": False, "error": f"button not clickable: {exc}", "wanted": button_text}


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
    if backend == "pywinauto":
        result = _click_button_pywinauto(handle, click_label)
    else:
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


def auto_dismiss(*, only_known: bool = True) -> dict[str, Any]:
    """Click through known (or all matching) dialogs using preferred buttons."""
    listing = list_dialogs(include_main_windows=True)
    if not listing.get("ok"):
        return listing

    handled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for d in listing.get("dialogs") or []:
        title = d.get("title") or ""
        process = d.get("process_name") or ""
        spec = _known_match(title, process)
        if only_known and not spec:
            skipped.append({"title": title, "hwnd": d.get("hwnd"), "reason": "not_known"})
            continue
        buttons_pref: tuple[str, ...]
        if spec:
            buttons_pref = tuple(spec.get("buttons") or ())
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
        if clicked:
            handled.append(
                {
                    "known_id": (spec or {}).get("id"),
                    "title": title,
                    "result": clicked,
                    "reason": (spec or {}).get("reason"),
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
    only_known: bool = True,
) -> dict[str, Any]:
    """Poll for dialogs and auto-dismiss until duration expires."""
    deadline = time.time() + max(0.0, duration_s)
    events: list[dict[str, Any]] = []
    while time.time() < deadline:
        res = auto_dismiss(only_known=only_known)
        if res.get("handled_count"):
            events.append({"t": time.time(), **res})
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
        res = auto_dismiss(only_known=only_known)
        if res.get("handled_count"):
            dismissed.extend(res.get("handled") or [])
        time.sleep(poll_s)
    return {"ok": False, "ready": False, "dismissed": dismissed, "error": "timeout"}
