# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Copy HephaestusBridge plugin template into a UE project."""

from __future__ import annotations

import shutil
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent
PLUGIN_TEMPLATE = FORGE_ROOT / "templates" / "ue_plugin" / "HephaestusBridge"

_SYNC_SKIP_DIRS = frozenset({"Intermediate", "Binaries", "__pycache__", ".vs", "DerivedDataCache"})


def _sync_ignore(_dir: str, names: list[str]) -> list[str]:
    return [n for n in names if n in _SYNC_SKIP_DIRS or n.endswith(".pyc")]


def sync_plugin(project_root: Path, dest: Path | None = None) -> Path:
    """Copy plugin template to {project}/Plugins/HephaestusBridge by default."""
    project_root = project_root.expanduser().resolve()
    if not PLUGIN_TEMPLATE.is_dir():
        raise FileNotFoundError(f"Plugin template missing: {PLUGIN_TEMPLATE}")
    target = dest or (project_root / "Plugins" / "HephaestusBridge")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        PLUGIN_TEMPLATE,
        target,
        dirs_exist_ok=True,
        ignore=_sync_ignore,
    )
    try:
        from version import BRIDGE_VERSION

        (target / "HEPHAESTUS_BRIDGE_VERSION").write_text(f"{BRIDGE_VERSION}\n", encoding="utf-8")
        version_header = (
            target / "Source" / "HephaestusBridge" / "Public" / "HephaestusVersion.h"
        )
        if version_header.is_file():
            text = version_header.read_text(encoding="utf-8")
            import re

            text = re.sub(
                r'#define HEPHAESTUS_BRIDGE_VERSION TEXT\("[^"]+"\)',
                f'#define HEPHAESTUS_BRIDGE_VERSION TEXT("{BRIDGE_VERSION}")',
                text,
                count=1,
            )
            version_header.write_text(text, encoding="utf-8")
    except Exception:
        pass
    return target
