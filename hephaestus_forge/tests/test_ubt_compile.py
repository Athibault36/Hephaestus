# Copyright (c) 2024 HephaestusForge. All Rights Reserved.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ubt_compile import build_ubt_compile_argv  # noqa: E402


def test_project_arg_has_no_nested_quotes(tmp_path: Path):
    uproject = tmp_path / "My Game" / "MyGame.uproject"
    uproject.parent.mkdir(parents=True)
    uproject.write_text("{}", encoding="utf-8")
    cmd = build_ubt_compile_argv(
        Path("C:/UE/UnrealBuildTool.exe"),
        project_name="MyGame",
        uproject=uproject,
    )
    project_flags = [c for c in cmd if c.startswith("-Project=")]
    assert len(project_flags) == 1
    assert '"' not in project_flags[0]
    assert "MyGame.uproject" in project_flags[0]
    assert cmd[1] == "MyGameEditor"


def test_clean_flag():
    cmd = build_ubt_compile_argv(
        "ubt",
        project_name="X",
        uproject=Path("C:/p/X.uproject"),
        clean=True,
    )
    assert "-Clean" in cmd
