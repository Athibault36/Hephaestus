"""HephaestusForge package."""

from __future__ import annotations

import sys
from pathlib import Path

# Flat sibling imports (preflight_health, ue_agent_loop, …) are used throughout.
# Ensure the package directory is on sys.path when installed as hephaestus_forge.
_PKG_DIR = Path(__file__).resolve().parent
_pkg = str(_PKG_DIR)
if _pkg not in sys.path:
    sys.path.insert(0, _pkg)
