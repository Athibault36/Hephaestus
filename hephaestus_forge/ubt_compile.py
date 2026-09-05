# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""UBT argv construction for forge compile."""

from __future__ import annotations

from pathlib import Path


def build_ubt_compile_argv(
    ubt_path: Path | str,
    *,
    project_name: str,
    uproject: Path | str,
    clean: bool = False,
) -> list[str]:
    """
    Build UnrealBuildTool argv for compiling a project's Editor target.

    Critical: ``-Project=`` must not wrap the path in extra quotes when passed
    as a list element — nested quotes make UBT fail to find the .uproject.
    """
    uproject = Path(uproject).resolve()
    cmd = [
        str(ubt_path),
        f"{project_name}Editor",
        "Win64",
        "Development",
        f"-Project={uproject}",
        "-NoEngineChanges",
    ]
    if clean:
        cmd.append("-Clean")
    return cmd
