# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Hephaestus Python API Package
Provides high-level Python bindings for UE5.8 agent operations.
"""

__version__ = "1.0.0"
__all__ = ["commands", "pcg", "niagara", "usd", "blender_ipc", "dcc_bridge"]


def __getattr__(name: str):
    if name in {"pcg", "niagara", "usd", "blender_ipc", "dcc_bridge", "commands"}:
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
