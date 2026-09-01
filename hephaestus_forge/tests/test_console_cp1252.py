# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Guard against Windows cp1252 console crashes (Phase 0 item 2).

`forge observe` / `forge scan` write to the Windows console, which defaults to
cp1252. Non-cp1252 glyphs (check marks, warning signs, arrows, emojis) raise
UnicodeEncodeError there and crash the CLI. These tests keep console output
cp1252-safe.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORGE = ROOT / "forge.py"

# Glyphs that are outside cp1252 and previously crashed the console.
FORBIDDEN_GLYPHS = ["\u2713", "\u2717", "\u26a0", "\U0001f50d", "\U0001f4e6", "\U0001f3d7"]


def test_forge_source_has_no_forbidden_console_glyphs():
    src = FORGE.read_text(encoding="utf-8")
    present = [g for g in FORBIDDEN_GLYPHS if g in src]
    assert present == [], f"non-cp1252 console glyphs still in forge.py: {present!r}"


def _run_under_cp1252(*args: str) -> tuple[int, str]:
    """Run the CLI with a cp1252 stdout/stderr, like a default Windows console.

    Output is captured as raw bytes and decoded as cp1252 so this harness does
    not itself choke on the (correct) cp1252 bytes the CLI emits. A cp1252
    UnicodeEncodeError inside the CLI would make it exit non-zero.
    """
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    proc = subprocess.run(
        [sys.executable, "-m", "hephaestus_forge.forge", *args],
        cwd=str(ROOT.parent),
        env=env,
        capture_output=True,
        timeout=120,
    )
    stderr = proc.stderr.decode("cp1252", errors="replace")
    return proc.returncode, stderr


def test_scan_renders_under_cp1252_console():
    code, stderr = _run_under_cp1252("scan")
    assert code == 0, stderr
    assert "UnicodeEncodeError" not in stderr


def test_help_renders_under_cp1252_console():
    code, stderr = _run_under_cp1252("--help")
    assert code == 0, stderr
    assert "UnicodeEncodeError" not in stderr


if __name__ == "__main__":
    test_forge_source_has_no_forbidden_console_glyphs()
    test_scan_renders_under_cp1252_console()
    test_help_renders_under_cp1252_console()
    print("ok")
