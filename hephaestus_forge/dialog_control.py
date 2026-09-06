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
        "id": "cc5_unsaved_project",
        "title_re": r"^Character Creator 5$",
        "process_re": r"CharacterCreator",
        "buttons": ("Cancel", "No", "OK"),
        "reason": "CC5 unsaved-project recovery prompt",
        "prefer_small": True,
        "body_re": r"Unsaved project|unsaved changes",
    },
    {
        "id": "cc5_apply_material",
        "title_re": r"^Apply Material$|Apply Material Settings|Material Settings",
        "process_re": r"CharacterCreator",
        "buttons": ("Apply", "OK", "Yes", "Continue"),
        "reason": "CC5 Apply Material blocks content/skin loads mid-job",
        "check_dont_show_again": True,
    },
    {
        "id": "cc5_apply_content",
        "title_re": r"^Apply (Morph|Pose|Motion|Cloth|Hair|Skin|Content)|^Load (Content|Item)|^Conform",
        "process_re": r"CharacterCreator",
        "buttons": ("Apply", "OK", "Yes", "Continue", "Load"),
        "reason": "CC5 apply/load content prompts during appearance",
        "check_dont_show_again": True,
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
        "title_re": r"^Message$|^Warning$|^Error$|^Confirm$|^Information$|^Notice$",
        "process_re": r"CharacterCreator",
        "buttons": ("OK", "Yes", "Continue", "Close", "Cancel"),
        "reason": "CC5 MessageBox",
    },
    {
        "id": "cc5_qt_modal",
        "title_re": r"^Character Creator 5$",
        "process_re": r"CharacterCreator",
        "buttons": ("Cancel", "OK", "No", "Yes", "Close", "Apply"),
        "reason": "CC5 Qt modal with generic title",
        "prefer_small": True,
    },
    {
        "id": "cc5_please_wait",
        "title_re": r"Please wait|Please Wait",
        "process_re": r"CharacterCreator",
        "buttons": (),
        "skip_auto": True,
        "reason": "Progress dialog — wait, do not cancel",
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
            width = height = 0
            try:
                rect = w.rectangle()
                width, height = int(rect.width()), int(rect.height())
            except Exception:
                pass
            is_qt = "qt" in class_name.lower()
            is_small = 0 < height < 500 and 0 < width < 900
            # Prefer modal-ish / dialog classes, but keep titled top-levels that look like prompts
            is_dialogish = (
                "dialog" in class_name.lower()
                or class_name in ("#32770",)
                or bool(_known_match(title, ""))
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
                        "apply",
                        "material",
                        "morph",
                        "export",
                        "import",
                        "overwrite",
                        "please wait",
                    )
                )
                or (is_qt and is_small)
            )
            if not is_dialogish and class_name not in ("#32770",):
                # Skip huge main frames
                if height > 700 and width > 900:
                    continue
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
            body = ""
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
            # CC5 Qt modals need UIA to see OK/Cancel
            if (not buttons) and (
                is_qt or "charactercreator" in (process_name or "").lower()
            ):
                buttons, body = _uia_buttons_and_body(int(w.handle))

            known = _known_match(title, process_name) or {}
            # Prefer unsaved-project spec when body text matches
            if body and re.search(r"Unsaved project|unsaved changes", body, re.I):
                for spec in KNOWN_DIALOGS:
                    if spec.get("id") == "cc5_unsaved_project":
                        known = spec
                        break
            # Skip large main windows for prefer_small known dialogs
            if known.get("prefer_small") and not is_small and height > 500:
                known = {}
                # Still keep if UIA found OK/Cancel on a mid-size window
                if not (buttons and any(_normalize(b) in ("ok", "cancel") for b in buttons)):
                    if title.lower() == "character creator 5" and height > 500:
                        continue

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
                for k in (
                    "restore",
                    "save",
                    "crash",
                    "error",
                    "warning",
                    "confirm",
                    "message",
                    "apply",
                    "material",
                    "morph",
                    "export",
                    "import",
                    "overwrite",
                )
            ):
                filtered.append(d)
            elif (
                "qt" in (d.class_name or "").lower()
                and "charactercreator" in (d.process_name or "").lower()
                and d.title.strip().lower() in ("character creator 5", "apply material")
            ):
                # Small CC5 Qt modals (not the main editor frame)
                filtered.append(d)
        dialogs = filtered

    return {
        "ok": True,
        "backend": backend,
        "count": len(dialogs),
        "dialogs": [d.to_dict() for d in dialogs],
    }


def _uia_buttons_and_body(hwnd: int) -> tuple[list[str], str]:
    """Enumerate Qt/UIA buttons and static text (CC5 modals are not win32 Buttons)."""
    buttons: list[str] = []
    body_bits: list[str] = []
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(handle=int(hwnd))
        win = app.window(handle=int(hwnd))
        for ctrl in win.descendants():
            try:
                ctype = (ctrl.element_info.control_type or "").lower()
                text = (ctrl.window_text() or "").strip()
                if not text:
                    continue
                if ctype == "button" and text not in buttons:
                    buttons.append(text)
                elif ctype in ("text", "document", "edit", "checkbox", "check box") and len(text) > 3:
                    body_bits.append(text)
            except Exception:
                continue
    except Exception:
        pass
    return buttons, " ".join(body_bits)


def _check_dont_show_again(hwnd: int) -> dict[str, Any]:
    """Tick 'Don't show this again' on CC5 Apply Material / similar Qt dialogs."""
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(handle=int(hwnd))
        win = app.window(handle=int(hwnd))
        needles = (
            "don't show this again",
            "dont show this again",
            "do not show this again",
            "don't show again",
        )
        for ctrl in win.descendants():
            try:
                ctype = (ctrl.element_info.control_type or "").lower()
                if ctype not in ("checkbox", "check box"):
                    continue
                text = _normalize(ctrl.window_text() or "")
                if not any(n in text for n in needles):
                    continue
                try:
                    if hasattr(ctrl, "get_toggle_state") and ctrl.get_toggle_state() == 1:
                        return {"ok": True, "checked": True, "already": True}
                except Exception:
                    pass
                try:
                    ctrl.toggle()
                except Exception:
                    try:
                        ctrl.click_input()
                    except Exception as exc:
                        return {"ok": False, "error": str(exc)}
                return {"ok": True, "checked": True, "method": "uia_checkbox"}
            except Exception:
                continue
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "dont_show_checkbox_not_found"}


def _click_button_uia(hwnd: int, button_text: str) -> dict[str, Any]:
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(handle=int(hwnd))
        win = app.window(handle=int(hwnd))
        try:
            win.set_focus()
        except Exception:
            pass
        # Exact title
        try:
            btn = win.child_window(title=button_text, control_type="Button")
            if btn.exists(timeout=0.5):
                btn.invoke()
                return {"ok": True, "clicked": button_text, "method": "uia_invoke"}
        except Exception:
            pass
        for ctrl in win.descendants(control_type="Button"):
            try:
                text = (ctrl.window_text() or "").strip()
                if _normalize(text) == _normalize(button_text) or _normalize(button_text) in _normalize(
                    text
                ):
                    try:
                        ctrl.invoke()
                    except Exception:
                        ctrl.click()
                    return {"ok": True, "clicked": text, "method": "uia_enumerate"}
            except Exception:
                continue
        return {"ok": False, "error": f"uia button not found: {button_text}", "wanted": button_text}
    except Exception as exc:
        return {"ok": False, "error": f"uia click failed: {exc}", "wanted": button_text}


def _click_button_pywinauto(hwnd: int, button_text: str) -> dict[str, Any]:
    # Prefer win32 BM_CLICK first — click_input fails across integrity levels
    # when Unreal was started elevated and forge was not (UIPI).
    win32_res = _click_button_win32(hwnd, button_text)
    if win32_res.get("ok"):
        win32_res["method"] = "BM_CLICK_first"
        return win32_res
    # Qt (CC5) dialogs expose buttons only via UIA.
    uia_res = _click_button_uia(hwnd, button_text)
    if uia_res.get("ok"):
        return uia_res
    err = str(win32_res.get("error") or "")
    if "not found" not in err.lower():
        return {
            "ok": False,
            "error": (
                f"win32 click failed (skipping click_input to avoid UIPI hang): {err}; "
                f"uia={uia_res.get('error')}"
            ),
            "wanted": button_text,
        }
    from pywinauto import Application

    app = Application(backend="win32").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    try:
        win.child_window(title=button_text, class_name="Button").click()
        return {"ok": True, "clicked": button_text, "method": "title_click"}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"button not clickable: {exc}; win32={err}; uia={uia_res.get('error')}",
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
    if not result.get("ok"):
        result = _click_button_uia(handle, click_label)
    if not result.get("ok") and backend == "pywinauto":
        result = _click_button_pywinauto(handle, click_label)

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


def _dismiss_cc5_embedded_modals() -> list[dict[str, Any]]:
    """
    CC5 often shows Apply Material as a Qt dialog that is not a top-level
    EnumWindows target. Find by win32 child titles first (fast), then UIA BFS
    under CharacterCreator mains (depth-limited — never full descendants()).
    """
    handled: list[dict[str, Any]] = []
    if sys.platform != "win32":
        return handled
    try:
        import psutil
        import win32gui
        import win32process
    except Exception as exc:
        return [{"ok": False, "error": f"deps: {exc}"}]

    cc5_pids = {
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name"])
        if "charactercreator" in ((p.info.get("name") or "").lower())
        and "py" not in ((p.info.get("name") or "").lower())
    }
    if not cc5_pids:
        return handled

    title_needles = (
        "apply material",
        "apply morph",
        "apply pose",
        "apply cloth",
        "apply hair",
        "apply skin",
        "apply content",
    )
    matches: list[tuple[int, str]] = []
    # Small generic CC5 Qt modals (title often just "Character Creator 5")
    cc5_small_modals: list[int] = []

    def _pid_of(hwnd: int) -> int:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return int(pid)
        except Exception:
            return 0

    def _consider(hwnd: int) -> None:
        try:
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            if not title:
                return
            if _pid_of(hwnd) not in cc5_pids:
                return
            title_l = title.lower()
            visible = bool(win32gui.IsWindowVisible(hwnd))
            if any(n in title_l for n in title_needles) and visible:
                matches.append((int(hwnd), title))
                return
            # Visible small "Character Creator 5" dialogs often host Apply Material chrome
            if visible and title_l == "character creator 5":
                try:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    w, h = right - left, bottom - top
                    if 180 < w < 900 and 120 < h < 700:
                        cc5_small_modals.append(int(hwnd))
                except Exception:
                    pass
        except Exception:
            return

    def _enum_child(hwnd, _):
        _consider(hwnd)
        return True

    def _enum_top(hwnd, _):
        try:
            if _pid_of(hwnd) in cc5_pids:
                _consider(hwnd)
                win32gui.EnumChildWindows(hwnd, _enum_child, None)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_enum_top, None)
    except Exception as exc:
        return [{"ok": False, "error": f"enum: {exc}"}]

    # Probe small CC5 modals for an Apply button (covers painted-title Qt dialogs)
    for hwnd in cc5_small_modals:
        try:
            buttons, body = _uia_buttons_and_body(hwnd)
        except Exception:
            continue
        btn_l = {_normalize(b) for b in buttons}
        body_l = _normalize(body)
        if "apply" in btn_l or "don't show this again" in body_l or "dont show this again" in body_l:
            matches.append((hwnd, "Character Creator 5 / Apply Material"))

    # Optional deep UIA name search — only when a small modal exists but Apply wasn't
    # enumerated yet (avoids walking the huge main-frame tree every poll).
    if not matches and cc5_small_modals:
        deadline = time.time() + 0.8
        try:
            from collections import deque
            from pywinauto import Application

            for hwnd in cc5_small_modals:
                if time.time() > deadline:
                    break
                try:
                    app = Application(backend="uia").connect(handle=int(hwnd))
                    root = app.window(handle=int(hwnd))
                except Exception:
                    continue
                q: deque = deque([(root, 0)])
                while q and time.time() <= deadline:
                    el, depth = q.popleft()
                    try:
                        name = (el.window_text() or getattr(el.element_info, "name", "") or "").strip()
                    except Exception:
                        name = ""
                    if name and any(n in name.lower() for n in title_needles):
                        matches.append((int(hwnd), name))
                        break
                    if depth >= 3:
                        continue
                    try:
                        for child in el.children():
                            q.append((child, depth + 1))
                    except Exception:
                        continue
                if matches:
                    break
        except Exception:
            pass

    seen: set[int] = set()
    for hwnd, title in matches:
        if hwnd in seen:
            continue
        seen.add(hwnd)
        try:
            _check_dont_show_again(hwnd)
        except Exception:
            pass
        clicked = None
        for label in ("Apply", "OK", "Yes", "Continue"):
            try:
                res = _click_button_uia(hwnd, label)
            except Exception as exc:
                res = {"ok": False, "error": str(exc)}
            if res.get("ok"):
                clicked = res
                break
            try:
                res2 = _click_button_win32(hwnd, label)
            except Exception as exc:
                res2 = {"ok": False, "error": str(exc)}
            if res2.get("ok"):
                clicked = res2
                break
        if clicked and clicked.get("ok"):
            handled.append(
                {
                    "known_id": "cc5_apply_material",
                    "title": title,
                    "result": clicked,
                    "reason": "CC5 embedded Apply Material / content modal",
                    "hwnd": hwnd,
                }
            )
    return handled


def auto_dismiss(*, only_known: bool = True, target_processes_only: bool = True) -> dict[str, Any]:
    """
    Dismiss Hephaestus-relevant dialogs.

    - Known UE/CC5 dialogs (Restore Packages, FBX Import, Message Log, Apply Material, …)
    - Embedded CC5 Qt child modals (Apply Material under the main frame)
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

    # Always sweep CC5 embedded Apply Material first — these are not top-level.
    try:
        for ev in _dismiss_cc5_embedded_modals():
            if ev.get("known_id") and isinstance(ev.get("result"), dict) and ev["result"].get("ok"):
                handled.append(ev)
            elif ev.get("error"):
                skipped.append(ev)
    except Exception as exc:
        skipped.append({"reason": "embedded_sweep_failed", "error": str(exc)})

    for d in listing.get("dialogs") or []:
        title = d.get("title") or ""
        process = d.get("process_name") or ""
        class_name = d.get("class_name") or ""
        if target_processes_only and process and not _target_process(process):
            continue
        if target_processes_only and not process:
            # Empty process attribution: match known titles without forcing UE process_re
            if not _known_match(title, ""):
                continue

        spec = _known_match(title, process or "")
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
                    "apply",
                    "material",
                    "morph",
                    "cloth",
                    "conform",
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

        if spec and spec.get("check_dont_show_again"):
            _check_dont_show_again(int(d["hwnd"]))

        available = list(d.get("buttons") or [])
        clicked = None
        last_err = None
        # Known Apply dialogs: try Apply even before button enumeration
        if spec and "Apply" in (spec.get("buttons") or ()) and "Apply" not in available:
            available = ["Apply"] + available
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
            # No enumerated buttons — try Apply/OK then close
            for label in ("Apply", "OK", "Yes", "Close", "Cancel"):
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
