"""Pure helpers for locating a UE project/engine and building UBT commands.

Kept free of side effects (no process launches) so command construction can be
unit tested on any OS, while the ``forge compile`` command handles execution.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import List, Optional


def find_uproject(project_root: Path) -> Optional[Path]:
    """Locate the project's ``.uproject``.

    Searches the root first, then one directory level down (the repo keeps the
    UE project in a ``Hephaestus/`` subfolder). Prefers a file whose stem
    matches its parent directory name when several exist.
    """
    root = Path(project_root)
    candidates: List[Path] = sorted(root.glob("*.uproject"))
    if not candidates:
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            candidates.extend(sorted(child.glob("*.uproject")))
    if not candidates:
        return None
    for c in candidates:
        if c.stem.lower() == c.parent.name.lower():
            return c
    return candidates[0]


def resolve_ue_root(config_ue_path: Optional[str] = None, env: Optional[dict] = None) -> Optional[Path]:
    """Resolve the Unreal Engine root from config, environment, or common paths."""
    env = env if env is not None else os.environ
    for candidate in (
        config_ue_path,
        env.get("UE_PATH"),
        env.get("UE5_PATH"),
        env.get("UNREAL_ENGINE_PATH"),
    ):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    # Common default install locations by OS.
    guesses = [
        Path("C:/Program Files/Epic Games/UE_5.8"),
        Path("C:/UnrealEngine/5.8"),
        Path.home() / "UnrealEngine" / "5.8",
        Path("/opt/UnrealEngine/5.8"),
        Path("/Users/Shared/Epic Games/UE_5.8"),
    ]
    for g in guesses:
        if g.exists():
            return g
    return None


def _batchfiles_dir(ue_root: Path, target_platform: str) -> Path:
    base = ue_root / "Engine" / "Build" / "BatchFiles"
    if target_platform == "Win64":
        return base
    if target_platform == "Mac":
        return base / "Mac"
    return base / "Linux"


def build_script_path(ue_root: Path, target_platform: str) -> Path:
    """Path to the platform-appropriate Build script."""
    script = "Build.bat" if target_platform == "Win64" else "Build.sh"
    return _batchfiles_dir(ue_root, target_platform) / script


def default_target_platform() -> str:
    system = platform.system()
    if system == "Windows":
        return "Win64"
    if system == "Darwin":
        return "Mac"
    return "Linux"


def editor_target_name(uproject: Path) -> str:
    """The editor build target for a project (e.g. ``HephaestusEditor``)."""
    return f"{uproject.stem}Editor"


def link_plugin(project_root: Path, plugin_source_rel: str) -> tuple[Path, str]:
    """Ensure the plugin is discoverable under ``<project>/Plugins/<Name>``.

    The scaffold places sources under a non-standard dir (e.g.
    ``UE5_Plugin_Source/HephaestusBridge``), but Unreal only auto-discovers
    plugins in ``Plugins/``. This links (or copies as a fallback) the source
    into place. Returns ``(dest_path, action)`` where action is one of
    ``exists`` | ``linked`` | ``copied`` | ``missing-source``.
    """
    import os
    import shutil

    source = (project_root / plugin_source_rel).resolve()
    dest = project_root / "Plugins" / source.name
    if not source.exists():
        return dest, "missing-source"
    if dest.exists():
        return dest, "exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(source, dest, target_is_directory=True)
        return dest, "linked"
    except (OSError, NotImplementedError):
        shutil.copytree(source, dest)
        return dest, "copied"


def build_ubt_command(
    ue_root: Path,
    uproject: Path,
    *,
    target: Optional[str] = None,
    target_platform: Optional[str] = None,
    configuration: str = "Development",
    clean: bool = False,
) -> List[str]:
    """Construct the UnrealBuildTool command to compile the project editor target.

    Building the editor target compiles all project modules, including the
    HephaestusBridge plugin.
    """
    tp = target_platform or default_target_platform()
    tgt = target or editor_target_name(uproject)
    script = build_script_path(ue_root, tp)
    cmd = [str(script), tgt, tp, configuration, f"-project={uproject}", "-waitmutex"]
    if clean:
        cmd.append("-clean")
    return cmd
