# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
PIE smoke test for world.spawn_actor.

Usage (Unreal Output Log / Python console, while Play-In-Editor is running):

    import unreal
    unreal.PythonScriptLibrary.execute_python_command(
        r"exec(open(r'C:/Users/Alex/OneDrive/Documents/Unreal Projects/test/Plugins/HephaestusBridge/Content/Python/hephaestus/smoke_spawn_actor.py').read())"
    )

Or from the Output Log Python input after adding the plugin Content/Python path:

    import hephaestus.commands as hc
    print(hc.smoke_spawn_point_light((0, 0, 200)))
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure plugin Python package is importable when run via exec(open(...))
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from hephaestus.commands import smoke_spawn_point_light  # noqa: E402


def main() -> None:
    result = smoke_spawn_point_light((0.0, 0.0, 200.0))
    print(json.dumps(result, indent=2))
    if not result.get("success"):
        raise SystemExit(f"SMOKE FAILED: {result.get('error')}")
    print("SMOKE OK — PointLight spawned via world.spawn_actor")


if __name__ == "__main__":
    main()
