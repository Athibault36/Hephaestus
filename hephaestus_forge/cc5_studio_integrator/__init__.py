# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
CC5 Studio Integrator — Hephaestus entry points for programmatic Character Creator control.

This package is the studio-facing API. It wraps the existing OpenPlugin job queue,
appearance planner, dialog dismisser, FBX+.fbm export, and UE 5.8 HephaestusBridge
import/animation path. See README.md for the honest capability matrix.
"""

from __future__ import annotations

from .animation import generate_animation
from .audit import audit_log
from .capabilities import INTEGRATOR_VERSION, capability_report
from .configure import configure_character
from .export import export_asset
from .session import (
    detach_cc5_control,
    get_session,
    initialize_cc5_session,
    rollback_cc5_configuration,
    terminate_cc5_session,
)

__version__ = INTEGRATOR_VERSION

__all__ = [
    "INTEGRATOR_VERSION",
    "initialize_cc5_session",
    "configure_character",
    "generate_animation",
    "export_asset",
    "terminate_cc5_session",
    "detach_cc5_control",
    "rollback_cc5_configuration",
    "get_session",
    "capability_report",
    "audit_log",
]
