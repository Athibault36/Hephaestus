# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Build and prepare Mission Control dashboard assets."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

FACTORY_TEMPLATE = Path(__file__).resolve().parent / "templates" / "mission_control"


def is_vite_build(dist_dir: Path) -> bool:
    """True when dist looks like a Vite production build (not inline fallback HTML)."""
    index = dist_dir / "index.html"
    if not index.is_file():
        return False
    if (dist_dir / "assets").is_dir():
        return True
    text = index.read_text(encoding="utf-8", errors="replace")
    return 'src="/assets/' in text or "src='./assets/" in text


def ensure_mission_control_source(project_root: Path, mission_control_dir: str = "MissionControl") -> Path:
    mc_dir = project_root / mission_control_dir
    if (mc_dir / "package.json").is_file():
        return mc_dir
    if not FACTORY_TEMPLATE.is_dir():
        raise FileNotFoundError(f"Mission Control template missing: {FACTORY_TEMPLATE}")
    shutil.copytree(FACTORY_TEMPLATE, mc_dir, dirs_exist_ok=True)
    return mc_dir


def build_mission_control(
    project_root: Path,
    *,
    mission_control_dir: str = "MissionControl",
) -> Path:
    """npm ci + vite build into {project}/MissionControl/dist."""
    mc_dir = ensure_mission_control_source(project_root, mission_control_dir)
    npm = "npm.cmd" if shutil.which("npm.cmd") else "npm"
    if not shutil.which(npm):
        raise RuntimeError("npm not found — install Node.js to build the React Mission Control UI")
    subprocess.run([npm, "ci"], cwd=mc_dir, check=True)
    subprocess.run([npm, "run", "build"], cwd=mc_dir, check=True)
    dist = mc_dir / "dist"
    if not is_vite_build(dist):
        raise RuntimeError(f"Vite build did not produce assets in {dist}")
    return dist


def prepare_mission_control_dist(
    project_root: Path,
    mission_control_dir: str,
    *,
    force_static: bool,
    write_fallback: Callable[[Path, str], None],
) -> Path:
    """
    Return dist directory for observe/desktop.

    Keeps an existing Vite build unless force_static=True, then writes inline HTML fallback.
    """
    dist_dir = project_root / mission_control_dir / "dist"
    if not force_static and is_vite_build(dist_dir):
        return dist_dir
    write_fallback(dist_dir, "")
    return dist_dir
