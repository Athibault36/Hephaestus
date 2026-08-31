"""Agent tools that map high-level intents to HephaestusBridge commands.

Each :class:`Tool` knows how to turn keyword arguments into the exact JSON
envelope the UE command handler expects and how to advertise itself to an
LLM via an OpenAI-style function schema. Tools are pure translation + a call
through :class:`~hephaestus_forge.runtime.ue_client.UEClient`; all engine work
happens in the plugin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ue_client import CommandResult, UEClient

Vec3 = Tuple[float, float, float]


class ToolError(Exception):
    """Raised for unknown tools or invalid tool arguments (not engine failures)."""


@dataclass
class ToolResult:
    """Normalized outcome of a tool invocation, safe to feed back to an LLM."""

    tool: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    actor_references: List[str] = field(default_factory=list)
    asset_references: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0

    @classmethod
    def from_command(cls, tool: str, result: CommandResult) -> "ToolResult":
        return cls(
            tool=tool,
            success=result.success,
            data=result.result,
            error=result.error_message,
            actor_references=result.actor_references,
            asset_references=result.asset_references,
            execution_time_ms=result.execution_time_ms,
        )

    def to_summary(self) -> Dict[str, Any]:
        """Compact dict for LLM consumption / logging."""
        summary: Dict[str, Any] = {"success": self.success}
        if self.data:
            summary["result"] = self.data
        if self.actor_references:
            summary["actors"] = self.actor_references
        if self.asset_references:
            summary["assets"] = self.asset_references
        if not self.success:
            summary["error"] = self.error or "command failed"
        return summary


@dataclass
class Tool:
    """A single agent capability backed by a UE command."""

    name: str
    description: str
    parameters: Dict[str, Any]
    builder: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any]]]

    def openai_schema(self) -> Dict[str, Any]:
        """Return the OpenAI tool/function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name.replace(".", "__"),
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def invoke(self, client: UEClient, args: Dict[str, Any]) -> ToolResult:
        command, params = self.builder(args or {})
        result = client.execute(command, params)
        return ToolResult.from_command(self.name, result)


class ToolRegistry:
    """Holds the tools available to an agent and dispatches invocations."""

    def __init__(self, tools: Optional[List[Tool]] = None):
        self._tools: Dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        # Also index by the LLM-safe alias (dots are illegal in some schemas).
        self._tools[tool.name.replace(".", "__")] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name) or self._tools.get(name.replace("__", "."))
        if tool is None:
            raise ToolError(f"Unknown tool: {name}")
        return tool

    def names(self) -> List[str]:
        return sorted({t.name for t in self._tools.values()})

    def openai_schemas(self) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        schemas: List[Dict[str, Any]] = []
        for tool in self._tools.values():
            if tool.name in seen:
                continue
            seen.add(tool.name)
            schemas.append(tool.openai_schema())
        return schemas

    def execute(self, client: UEClient, name: str, args: Optional[Dict[str, Any]] = None) -> ToolResult:
        return self.get(name).invoke(client, args or {})


# --- argument helpers -------------------------------------------------------
def _as_vec3(value: Any, default: Vec3) -> Dict[str, float]:
    """Coerce a scalar, 3-sequence, or {x,y,z} mapping into a UE vector dict."""
    if value is None:
        x, y, z = default
    elif isinstance(value, (int, float)):
        x = y = z = float(value)
    elif isinstance(value, dict):
        x = float(value.get("x", default[0]))
        y = float(value.get("y", default[1]))
        z = float(value.get("z", default[2]))
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        x, y, z = (float(v) for v in value)
    else:
        raise ToolError(f"Expected scalar, [x,y,z], or {{x,y,z}}, got {value!r}")
    return {"x": x, "y": y, "z": z}


def _as_rotator(value: Any) -> Dict[str, float]:
    if value is None:
        p = yaw = roll = 0.0
    elif isinstance(value, dict):
        p = float(value.get("pitch", 0.0))
        yaw = float(value.get("yaw", 0.0))
        roll = float(value.get("roll", 0.0))
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        p, yaw, roll = (float(v) for v in value)
    else:
        raise ToolError(f"Expected [pitch,yaw,roll] or {{pitch,yaw,roll}}, got {value!r}")
    return {"pitch": p, "yaw": yaw, "roll": roll}


# --- concrete tool builders -------------------------------------------------
def _build_spawn_actor(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    class_path = args.get("class_path")
    if not class_path or not isinstance(class_path, str):
        raise ToolError("world.spawn_actor requires a string 'class_path'")
    params: Dict[str, Any] = {
        "action": "spawn_actor",
        "class_path": class_path,
        "transform": {
            "location": _as_vec3(args.get("location"), (0.0, 0.0, 0.0)),
            "rotation": _as_rotator(args.get("rotation")),
            "scale": _as_vec3(args.get("scale"), (1.0, 1.0, 1.0)),
        },
    }
    if args.get("label"):
        params["label"] = str(args["label"])
    return "world.spawn_actor", params


def _build_destroy_actor(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    actor_path = args.get("actor_path")
    if not actor_path or not isinstance(actor_path, str):
        raise ToolError("world.destroy_actor requires a string 'actor_path'")
    return "world.destroy_actor", {"action": "destroy_actor", "actor_path": actor_path}


def _build_query_spatial(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {"action": "query_spatial"}
    if args.get("filter_class"):
        params["filter_class"] = str(args["filter_class"])
    if args.get("center") is not None or args.get("extent") is not None:
        params["bounds"] = {
            "center": _as_vec3(args.get("center"), (0.0, 0.0, 0.0)),
            "extent": _as_vec3(args.get("extent"), (1000.0, 1000.0, 1000.0)),
        }
    return "world.query_spatial", params


def _build_capture_frame(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {"action": "capture_frame"}
    if args.get("format"):
        params["format"] = str(args["format"])
    if args.get("width") and args.get("height"):
        params["resolution"] = {"width": int(args["width"]), "height": int(args["height"])}
    return "vision.capture_frame", params


SPAWN_ACTOR = Tool(
    name="world.spawn_actor",
    description=(
        "Spawn an actor in the running UE level from a class path (e.g. a "
        "Blueprint or native class), at an optional location/rotation/scale. "
        "Returns the spawned actor's path."
    ),
    parameters={
        "type": "object",
        "properties": {
            "class_path": {
                "type": "string",
                "description": "Object path of the actor class, e.g. '/Game/BP/BP_Cube.BP_Cube_C' or '/Script/Engine.StaticMeshActor'.",
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "description": "World location [x, y, z] in cm. Defaults to [0,0,0].",
            },
            "rotation": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Rotation [pitch, yaw, roll] in degrees. Defaults to [0,0,0].",
            },
            "scale": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Scale [x, y, z] or a single uniform number. Defaults to [1,1,1].",
            },
            "label": {"type": "string", "description": "Optional editor label for the actor."},
        },
        "required": ["class_path"],
    },
    builder=_build_spawn_actor,
)

DESTROY_ACTOR = Tool(
    name="world.destroy_actor",
    description="Destroy an actor identified by its full path name.",
    parameters={
        "type": "object",
        "properties": {
            "actor_path": {"type": "string", "description": "Full path of the actor to destroy."}
        },
        "required": ["actor_path"],
    },
    builder=_build_destroy_actor,
)

QUERY_SPATIAL = Tool(
    name="world.query_spatial",
    description="Query actors in the level, optionally filtered by class and a bounding box.",
    parameters={
        "type": "object",
        "properties": {
            "filter_class": {"type": "string", "description": "Optional class path to filter by."},
            "center": {"type": "array", "items": {"type": "number"}, "description": "Box center [x,y,z]."},
            "extent": {"type": "array", "items": {"type": "number"}, "description": "Box half-extent [x,y,z]."},
        },
    },
    builder=_build_query_spatial,
)

CAPTURE_FRAME = Tool(
    name="vision.capture_frame",
    description=(
        "Capture a single frame of the UE viewport for the observe loop. Returns "
        "frame metadata (frame_id, width, height) the agent can reason about."
    ),
    parameters={
        "type": "object",
        "properties": {
            "format": {"type": "string", "description": "Optional capture format, e.g. 'RGBA8'."},
            "width": {"type": "integer", "description": "Optional capture width in pixels."},
            "height": {"type": "integer", "description": "Optional capture height in pixels."},
        },
    },
    builder=_build_capture_frame,
)

DEFAULT_TOOLS: List[Tool] = [SPAWN_ACTOR, DESTROY_ACTOR, QUERY_SPATIAL, CAPTURE_FRAME]


def build_default_registry() -> ToolRegistry:
    """Return a registry populated with the default UE agent tools."""
    return ToolRegistry(DEFAULT_TOOLS)
