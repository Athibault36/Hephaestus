"""HephaestusForge local-first agent runtime.

A small, dependency-light layer that lets a Python agent observe and act on a
running UE5.8 editor/game through the HephaestusBridge plugin:

- ``ue_client``   HTTP transport to the plugin's command handler.
- ``tools``       Typed tool registry (world.spawn_actor, vision.capture_frame, ...).
- ``llm``         Minimal OpenAI-compatible chat client with tool-calling.
- ``orchestrator``The observe -> think -> act loop (LLM -> tools -> UE).
"""

from .ue_client import CommandResult, UEClient, UEConnectionError, UEError
from .tools import Tool, ToolError, ToolRegistry, build_default_registry

__all__ = [
    "CommandResult",
    "UEClient",
    "UEConnectionError",
    "UEError",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "build_default_registry",
]
