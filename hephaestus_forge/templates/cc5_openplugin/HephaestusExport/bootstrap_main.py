# HEPHAESTUS_OPENPLUGIN_BOOTSTRAP 1
"""
Tiny Program Files stub — loads the real plugin from a user-writable path.

Updates go to ~/.hephaestus/cc5_openplugin_live/HephaestusExport (no Admin).
CC5 still requires this stub under Bin64/OpenPlugin/HephaestusExport/ once.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _live_main() -> Path:
    env = (os.environ.get("HEPHAESTUS_CC5_PLUGIN") or "").strip()
    if env:
        return Path(env)
    home = Path(os.environ.get("HEPHAESTUS_HOME") or (Path.home() / ".hephaestus"))
    return home / "cc5_openplugin_live" / "HephaestusExport" / "main.py"


def _load_live():
    live = _live_main()
    if not live.is_file():
        raise RuntimeError(
            f"Hephaestus CC5 live plugin missing: {live}. "
            "Run: forge cc5 install-plugin"
        )
    spec = importlib.util.spec_from_file_location("hephaestus_cc5_live", live)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Hephaestus CC5 plugin from {live}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hephaestus_cc5_live"] = mod
    spec.loader.exec_module(mod)
    return mod


_live = _load_live()
initialize_plugin = getattr(_live, "initialize_plugin")
# Forward any other CC5 entrypoints the host may call
for _name in ("run", "main", "start_plugin", "on_load"):
    if hasattr(_live, _name):
        globals()[_name] = getattr(_live, _name)
