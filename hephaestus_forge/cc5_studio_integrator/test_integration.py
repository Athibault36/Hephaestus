# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""CLI-friendly alias for the MRT (see tests/test_cc5_studio_integrator.py)."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tests" / "test_cc5_studio_integrator.py"),
        run_name="__main__",
    )
