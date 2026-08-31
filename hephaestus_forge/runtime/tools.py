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

from .errors import ErrorInfo, ToolError, infer_command_error, validation_error
from .validation import (
    validate_actor_path,
    validate_actor_path_list,
    validate_required_string,
    validate_spawn_class_path,
    validate_unreal_asset_path,
)
from .ue_client import CommandResult, UEClient

Vec3 = Tuple[float, float, float]


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
    error_kind: Optional[str] = None
    error_code: Optional[str] = None

    @classmethod
    def from_command(cls, tool: str, result: CommandResult) -> "ToolResult":
        err_kind = result.error_kind
        err_code = result.error_code
        if not result.success and not err_kind:
            inferred = infer_command_error(result.error_message)
            err_kind = inferred.kind.value
            err_code = inferred.code
        return cls(
            tool=tool,
            success=result.success,
            data=result.result,
            error=result.error_message,
            actor_references=result.actor_references,
            asset_references=result.asset_references,
            execution_time_ms=result.execution_time_ms,
            error_kind=err_kind,
            error_code=err_code,
        )

    @classmethod
    def failure(cls, tool: str, info: ErrorInfo) -> "ToolResult":
        return cls(
            tool=tool,
            success=False,
            error=info.message,
            error_kind=info.kind.value,
            error_code=info.code,
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
        if self.execution_time_ms:
            summary["execution_time_ms"] = self.execution_time_ms
        if not self.success:
            summary["error"] = self.error or "command failed"
            if self.error_kind:
                summary["error_kind"] = self.error_kind
            if self.error_code:
                summary["error_code"] = self.error_code
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
        try:
            command, params = self.builder(args or {})
        except ToolError as exc:
            info = getattr(exc, "info", None)
            if info:
                return ToolResult.failure(self.name, info)
            return ToolResult.failure(self.name, validation_error("TOOL_INVALID", str(exc)))
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
    class_path = validate_spawn_class_path(args.get("class_path"))
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
    actor_path = validate_actor_path(args.get("actor_path"))
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


def _build_batch_edit(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    actors = validate_actor_path_list(args.get("actors"))
    params: Dict[str, Any] = {
        "action": "batch_edit",
        "actors": actors,
        "property_edits": args.get("property_edits") or [],
    }
    return "world.batch_edit", params


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

BATCH_EDIT = Tool(
    name="world.batch_edit",
    description="Apply property edits to multiple actors in one command.",
    parameters={
        "type": "object",
        "properties": {
            "actors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Actor paths to edit.",
            },
            "property_edits": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {property, value} edits.",
            },
        },
        "required": ["actors"],
    },
    builder=_build_batch_edit,
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

def _require_str(args: Dict[str, Any], key: str, tool_name: str) -> str:
    value = args.get(key)
    if key in {"blueprint_path", "destination_path", "asset_path", "shader_path", "graph_path", "sequence_path"}:
        return validate_unreal_asset_path(value, key, tool_name)
    return validate_required_string(value, key, tool_name)


def _action_tool(
    name: str,
    action: str,
    description: str,
    required: List[str],
    optional: Optional[List[str]] = None,
) -> Tool:
    """Factory for tools whose params are ``action`` plus passthrough fields."""

    def builder(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        params: Dict[str, Any] = {"action": action}
        for key in required:
            params[key] = _require_str(args, key, name)
        for key in optional or []:
            if key in args and args[key] is not None:
                params[key] = args[key]
        return name, params

    properties: Dict[str, Any] = {
        key: {"type": "string", "description": f"Required {key}."} for key in required
    }
    for key in optional or []:
        properties[key] = {"type": "string", "description": f"Optional {key}."}

    return Tool(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": required,
        },
        builder=builder,
    )


# --- extended command families (C++ handlers; Python wiring testable now) ------
ASSET_CREATE_MATERIAL = _action_tool(
    "asset.create_material",
    "create_material",
    "Create a new material asset from a material description JSON/path.",
    required=["material_desc"],
)
ASSET_IMPORT = _action_tool(
    "asset.import",
    "import",
    "Import a file from disk into the UE content tree.",
    required=["file_path", "destination_path"],
    optional=["import_options"],
)
ASSET_REIMPORT = _action_tool("asset.reimport", "reimport", "Reimport an existing asset.", required=["asset_path"])
ASSET_EXPORT = _action_tool(
    "asset.export",
    "export",
    "Export a UE asset to disk.",
    required=["asset_path", "file_path"],
    optional=["export_options"],
)
ASSET_CREATE_INSTANCE = _action_tool(
    "asset.create_instance",
    "create_instance",
    "Create a material instance from a parent material.",
    required=["parent_material"],
    optional=["parameters"],
)

BLUEPRINT_COMPILE = _action_tool(
    "blueprint.compile",
    "compile",
    "Compile a Blueprint asset.",
    required=["blueprint_path"],
)
BLUEPRINT_ADD_FUNCTION = _action_tool(
    "blueprint.add_function",
    "add_function",
    "Add a function to a Blueprint.",
    required=["blueprint_path", "function_name"],
)
BLUEPRINT_SET_PROPERTY = _action_tool(
    "blueprint.set_property",
    "set_property",
    "Set a property on a Blueprint or generated class.",
    required=["blueprint_path", "property_name", "value"],
)
BLUEPRINT_DIFF = _action_tool(
    "blueprint.diff",
    "diff",
    "Diff a Blueprint against a prior revision or another asset.",
    required=["blueprint_path"],
    optional=["against_path"],
)

RENDERING_ADD_PASS = _action_tool(
    "rendering.add_pass",
    "add_pass",
    "Add a custom render pass to the viewport/renderer.",
    required=["pass_name"],
    optional=["pass_config"],
)
RENDERING_CREATE_SHADER_PARAMS = _action_tool(
    "rendering.create_shader_params",
    "create_shader_params",
    "Create shader parameter bindings for a material or pass.",
    required=["material_path"],
)
RENDERING_DISPATCH_COMPUTE = _action_tool(
    "rendering.dispatch_compute",
    "dispatch_compute",
    "Dispatch a compute shader with the given parameters.",
    required=["shader_path"],
    optional=["dispatch_size"],
)

PCG_MUTATE_GRAPH = _action_tool(
    "pcg.mutate_graph",
    "mutate_graph",
    "Apply a mutation to a PCG graph asset.",
    required=["graph_path"],
    optional=["mutation"],
)
PCG_SET_METADATA = _action_tool(
    "pcg.set_metadata",
    "set_metadata",
    "Set PCG metadata on actors or graph nodes.",
    required=["target_path", "metadata"],
)
PCG_QUERY_SPATIAL = _action_tool(
    "pcg.query_spatial",
    "query_spatial",
    "Query PCG-generated instances in a spatial region.",
    required=[],
    optional=["bounds", "filter_tag"],
)

ANIMATION_CREATE_CONTROL_RIG = _action_tool(
    "animation.create_control_rig",
    "create_control_rig",
    "Create a Control Rig asset for a skeletal mesh.",
    required=["skeletal_mesh_path"],
)
ANIMATION_RETARGET = _action_tool(
    "animation.retarget",
    "retarget",
    "Retarget animation between skeletons.",
    required=["source_skeleton", "target_skeleton", "sequence_path"],
)
ANIMATION_EDIT_SEQUENCE = _action_tool(
    "animation.edit_sequence",
    "edit_sequence",
    "Edit keys or sections on a level sequence.",
    required=["sequence_path"],
    optional=["edit_payload"],
)
ANIMATION_LIVELINK_CONNECT = _action_tool(
    "animation.livelink_connect",
    "livelink_connect",
    "Connect a LiveLink source for real-time animation.",
    required=["source_name"],
)

AUDIO_CREATE_METASOUND = _action_tool(
    "audio.create_metasound",
    "create_metasound",
    "Create a MetaSound source asset.",
    required=["asset_path"],
)
AUDIO_PLAY_QUARTZ = _action_tool(
    "audio.play_quartz",
    "play_quartz",
    "Start or schedule Quartz clock playback.",
    required=["clock_name"],
    optional=["quantization"],
)
AUDIO_SYNTHESIZE = _action_tool(
    "audio.synthesize",
    "synthesize",
    "Synthesize audio via MetaSound or procedural source.",
    required=["metasound_path"],
    optional=["duration_seconds"],
)

EXTENDED_TOOLS: List[Tool] = [
    ASSET_CREATE_MATERIAL,
    ASSET_IMPORT,
    ASSET_REIMPORT,
    ASSET_EXPORT,
    ASSET_CREATE_INSTANCE,
    BLUEPRINT_COMPILE,
    BLUEPRINT_ADD_FUNCTION,
    BLUEPRINT_SET_PROPERTY,
    BLUEPRINT_DIFF,
    RENDERING_ADD_PASS,
    RENDERING_CREATE_SHADER_PARAMS,
    RENDERING_DISPATCH_COMPUTE,
    PCG_MUTATE_GRAPH,
    PCG_SET_METADATA,
    PCG_QUERY_SPATIAL,
    ANIMATION_CREATE_CONTROL_RIG,
    ANIMATION_RETARGET,
    ANIMATION_EDIT_SEQUENCE,
    ANIMATION_LIVELINK_CONNECT,
    AUDIO_CREATE_METASOUND,
    AUDIO_PLAY_QUARTZ,
    AUDIO_SYNTHESIZE,
]

DEFAULT_TOOLS: List[Tool] = [SPAWN_ACTOR, DESTROY_ACTOR, QUERY_SPATIAL, BATCH_EDIT, CAPTURE_FRAME]


def build_default_registry(include_extended: bool = True) -> ToolRegistry:
    """Return a registry populated with core (and optionally extended) UE tools."""
    tools = list(DEFAULT_TOOLS)
    if include_extended:
        tools.extend(EXTENDED_TOOLS)
    return ToolRegistry(tools)
