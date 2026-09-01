# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
LLM planner for the UE observe→act loop (NVIDIA NIM OpenAI-compatible API).

Default model: deepseek-ai/deepseek-v4-pro-0813 @ https://integrate.api.nvidia.com/v1
Auth: NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY

Planner uses text over frame census + step memory by default. When
HEPHAESTUS_PLANNER_VISION=1, a multimodal caption (HEPHAESTUS_VISION_MODEL) is
prepended so text-only planners still get viewport context.
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from ue_agent_loop import AgentAction, WorldSnapshot, decide_action

try:
    from hephaestus_forge.cloud.nim_client import (
        DEFAULT_PLANNER_MODEL,
        DEFAULT_VISION_MODEL,
        chat_template_kwargs_for_model,
    )
except ImportError:
    from cloud.nim_client import (  # type: ignore
        DEFAULT_PLANNER_MODEL,
        DEFAULT_VISION_MODEL,
        chat_template_kwargs_for_model,
    )

DEFAULT_NIM_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NEMOTRON_MODEL = DEFAULT_PLANNER_MODEL  # backward-compatible name

SYSTEM_PROMPT = """You are HEPHAESTUS, an embodied Unreal Engine agent.
You receive a viewport census (and optional prior step memory). Choose exactly ONE next action.

Allowed JSON (no markdown):
{
  "action": "spawn_light" | "spawn_cube" | "spawn_mesh" | "spawn_character" | "play_anim" | "play_locomotion" | "play_montage" | "stop_anim" | "move_actor" | "apply_move" | "set_transform" | "set_light" | "set_view" | "create_shot" | "play_level_sequence" | "set_mesh_color" | "destroy" | "noop",
  "reason": "short why",
  "x": number, "y": number, "z": number,
  "yaw": number,
  "actor_path": "required for set_transform/set_light/destroy/play_anim/move_actor",
  "anim_path": "required for play_anim (UE anim sequence asset path)",
  "montage_path": "required for play_montage",
  "forward": number,
  "right": number,
  "duration": number,
  "intensity": number,
  "color": {"r":0-1,"g":0-1,"b":0-1},
  "attenuation_radius": number,
  "class_path": "only PointLight|SpotLight|StaticMeshActor allowlisted paths"
}

Rules:
- ALWAYS place new actors in front of the camera using the provided view location+forward
  (spawn ~300-600 cm along forward, near ground). Never use world origin unless view is missing.
- Prefer scale 2 for cubes so they are visible in the viewport capture.
- Prefer small reversible edits. |offset from view| should stay within a few meters.
- destroy/set_* only with actor_path from the provided interesting-actor list.
- set_light only on PointLight paths.
- set_view moves the player camera (location + rotation) for framing shots.
- create_shot animates camera to x/y/z over duration (cinematic pan; prefer for "frame" goals).
- play_level_sequence plays sequence_path Level Sequence asset (/Game/...).
- set_mesh_color tints a listed StaticMeshActor (color r/g/b 0-1).
- spawn_character spawns a skeletal mesh in view (cinematic/gameplay characters).
- play_anim plays anim_path on a listed SkeletalMeshActor path.
- play_locomotion plays idle|walk|run fallback on actor_path when anim_path is unknown.
- move_actor animates an actor toward x/y/z over duration seconds (walk into frame).
- apply_move applies forward/right input to the possessed pawn (gameplay jog/walk).
- play_montage plays montage_path on a listed character/skeletal actor.
- spawn_mesh uses mesh_path when spawning a static mesh (not only cubes).
- noop when goal is met (e.g. >=1 light and >=3 cubes IN VIEW for a basic seed goal).
- Use memory so you do not repeat the same failed or redundant spawn.
"""


def _system_prompt_for_goal(goal: str) -> str:
    goal_l = (goal or "").lower()
    if "[gameplay mode]" in goal_l:
        return (
            SYSTEM_PROMPT
            + "\nMode: gameplay — prefer apply_move on the possessed pawn; use play_montage on characters."
        )
    if "[cinematic mode]" in goal_l:
        return (
            SYSTEM_PROMPT
            + "\nMode: cinematic — prefer spawn_character, play_anim, move_actor, set_view; avoid pawn input unless asked."
        )
    return SYSTEM_PROMPT


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def _spawn_xyz_from_view(snapshot: WorldSnapshot, fallback_z: float = 100.0) -> tuple[float, float, float]:
    """Place spawns ~400cm along camera forward when planner omits coordinates."""
    view = snapshot.view or {}
    loc = view.get("location") if isinstance(view.get("location"), dict) else {}
    fwd = view.get("forward") if isinstance(view.get("forward"), dict) else {}
    if loc and fwd:
        lx, ly, lz = float(loc.get("x", 0)), float(loc.get("y", 0)), float(loc.get("z", 0))
        fx, fy, fz = float(fwd.get("x", 1)), float(fwd.get("y", 0)), float(fwd.get("z", 0))
        dist = 400.0
        return lx + fx * dist, ly + fy * dist, lz + fz * dist * 0.1 + fallback_z * 0.5
    return 0.0, 0.0, fallback_z


def plan_dict_to_action(plan: dict[str, Any], snapshot: WorldSnapshot) -> AgentAction:
    """Validate planner JSON into a Remote API command."""
    action = str(plan.get("action") or plan.get("kind") or "noop").strip().lower()
    reason = str(plan.get("reason") or "LLM plan")
    x = float(plan.get("x", 0.0))
    y = float(plan.get("y", 0.0))
    z = float(plan.get("z", 200.0))
    yaw = float(plan.get("yaw", 0.0))
    if action.startswith("spawn") and abs(x) < 1.0 and abs(y) < 1.0:
        x, y, z = _spawn_xyz_from_view(snapshot, fallback_z=z if z else 100.0)

    def transform(loc_z: float = z) -> dict[str, Any]:
        return {
            "location": {"x": x, "y": y, "z": loc_z},
            "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
        }

    if action in ("spawn_light", "spawn_point_light", "light"):
        class_path = str(plan.get("class_path") or "/Script/Engine.PointLight")
        return AgentAction(
            kind="spawn_light",
            reason=reason,
            command={
                "command": "world.spawn_actor",
                "params": {"class_path": class_path, "transform": transform(z if z else 280.0)},
            },
        )

    if action in ("spawn_cube", "spawn_mesh", "cube"):
        scale = float(plan.get("scale", 2.0))
        mesh_path = str(plan.get("mesh_path") or plan.get("mesh") or "/Engine/BasicShapes/Cube.Cube")
        return AgentAction(
            kind="spawn_cube",
            reason=reason,
            command={
                "command": "world.spawn_mesh",
                "params": {
                    "mesh_path": mesh_path,
                    "transform": {
                        "location": {"x": x, "y": y, "z": z if z else 100.0},
                        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                        "scale": {"x": scale, "y": scale, "z": scale},
                    },
                },
            },
        )

    if action in ("spawn_character", "spawn_skeletal", "character"):
        mesh_path = str(plan.get("mesh_path") or plan.get("mesh") or "")
        scale = float(plan.get("scale", 1.0))
        return AgentAction(
            kind="spawn_character",
            reason=reason,
            command={
                "command": "animation.spawn_skeletal_mesh",
                "params": {
                    "mesh_path": mesh_path,
                    "transform": {
                        "location": {"x": x, "y": y, "z": z if z else 100.0},
                        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
                        "scale": {"x": scale, "y": scale, "z": scale},
                    },
                },
            },
        )

    if action in ("play_anim", "play_animation", "play_sequence"):
        path = str(plan.get("actor_path") or "")
        anim_path = str(plan.get("anim_path") or plan.get("animation") or "")
        if path not in snapshot.actor_paths or not anim_path:
            return AgentAction(
                kind="noop",
                reason=f"Rejected play_anim — need listed skeletal actor + anim_path (got {path!r})",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="play_anim",
            reason=reason,
            command={
                "command": "animation.play_sequence",
                "params": {
                    "actor_path": path,
                    "anim_path": anim_path,
                    "loop": bool(plan.get("loop", False)),
                },
            },
        )

    if action in ("play_locomotion", "locomotion", "idle", "walk_in_place", "run_in_place"):
        path = str(plan.get("actor_path") or "")
        mode = str(plan.get("mode") or plan.get("locomotion") or action)
        if path not in snapshot.actor_paths:
            return AgentAction(
                kind="noop",
                reason=f"Rejected play_locomotion — unknown path: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="play_locomotion",
            reason=reason,
            command={
                "command": "animation.play_locomotion",
                "params": {
                    "actor_path": path,
                    "mode": mode,
                    "loop": bool(plan.get("loop", True)),
                },
            },
        )

    if action in ("play_montage", "montage"):
        path = str(plan.get("actor_path") or "")
        montage_path = str(plan.get("montage_path") or plan.get("montage") or "")
        if path not in snapshot.actor_paths or not montage_path:
            return AgentAction(
                kind="noop",
                reason=f"Rejected play_montage — need actor_path + montage_path",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="play_montage",
            reason=reason,
            command={
                "command": "animation.play_montage",
                "params": {
                    "actor_path": path,
                    "montage_path": montage_path,
                    "loop": bool(plan.get("loop", False)),
                },
            },
        )

    if action in ("stop_anim", "stop_animation", "stop"):
        path = str(plan.get("actor_path") or "")
        if path not in snapshot.actor_paths:
            return AgentAction(
                kind="noop",
                reason=f"Rejected stop_anim — unknown path: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="stop_anim",
            reason=reason,
            command={"command": "animation.stop", "params": {"actor_path": path}},
        )

    if action in ("apply_move", "jog", "walk_forward", "move_pawn"):
        forward = float(plan.get("forward", 1.0))
        right = float(plan.get("right", 0.0))
        duration = float(plan.get("duration", 2.0))
        return AgentAction(
            kind="apply_move",
            reason=reason,
            command={
                "command": "world.apply_move_input",
                "params": {"forward": forward, "right": right, "duration": duration},
            },
        )

    if action in ("move_actor", "walk_in", "cinematic_move"):
        path = str(plan.get("actor_path") or "")
        if path not in snapshot.actor_paths:
            return AgentAction(
                kind="noop",
                reason=f"Rejected move_actor — unknown path: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        duration = float(plan.get("duration", 3.0))
        return AgentAction(
            kind="move_actor",
            reason=reason,
            command={
                "command": "animation.play_transform_sequence",
                "params": {
                    "actor_path": path,
                    "target_location": {"x": x, "y": y, "z": z if z else 100.0},
                    "duration": duration,
                },
            },
        )

    if action in ("set_transform", "move", "teleport"):
        path = str(plan.get("actor_path") or "")
        if path not in snapshot.actor_paths:
            return AgentAction(
                kind="noop",
                reason=f"Rejected set_transform — unknown path: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="set_transform",
            reason=reason,
            command={
                "command": "world.set_transform",
                "params": {"actor_path": path, "transform": transform(z)},
            },
        )

    if action in ("set_view", "camera", "frame_shot"):
        pitch = float(plan.get("pitch", 0.0))
        duration = float(plan.get("duration", 0.0))
        loc = {"x": x, "y": y, "z": z if z else 200.0}
        rot = {"pitch": pitch, "yaw": yaw, "roll": 0.0}
        if duration > 0.1:
            return AgentAction(
                kind="create_shot",
                reason=reason,
                command={
                    "command": "sequence.create_shot",
                    "params": {
                        "location": loc,
                        "rotation": rot,
                        "duration": duration,
                        "actor_path": str(plan.get("actor_path") or ""),
                    },
                },
            )
        return AgentAction(
            kind="set_view",
            reason=reason,
            command={
                "command": "world.set_view",
                "params": {"transform": {"location": loc, "rotation": rot}},
            },
        )

    if action in ("create_shot", "camera_shot", "cinematic_shot", "sequence_shot"):
        pitch = float(plan.get("pitch", 0.0))
        duration = float(plan.get("duration", 4.0))
        actor_path = str(plan.get("actor_path") or "")
        shot_params: dict[str, Any] = {
            "location": {"x": x, "y": y, "z": z if z else 200.0},
            "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0.0},
            "duration": duration,
        }
        if actor_path:
            shot_params["actor_path"] = actor_path
            shot_params["target_location"] = {
                "x": float(plan.get("actor_x", x)),
                "y": float(plan.get("actor_y", y)),
                "z": float(plan.get("actor_z", z if z else 100.0)),
            }
        return AgentAction(
            kind="create_shot",
            reason=reason,
            command={"command": "sequence.create_shot", "params": shot_params},
        )

    if action in ("play_level_sequence", "play_sequence_asset", "sequence_play"):
        sequence_path = str(plan.get("sequence_path") or plan.get("path") or "")
        if not sequence_path:
            return AgentAction(
                kind="noop",
                reason="Rejected play_level_sequence — sequence_path required",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="play_level_sequence",
            reason=reason,
            command={
                "command": "sequence.play",
                "params": {
                    "sequence_path": sequence_path,
                    "loop": bool(plan.get("loop", False)),
                },
            },
        )

    if action in ("set_mesh_color", "color_mesh", "tint"):
        path = str(plan.get("actor_path") or "")
        if path not in snapshot.actor_paths:
            return AgentAction(
                kind="noop",
                reason=f"Rejected set_mesh_color — unknown path: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        color = plan.get("color") if isinstance(plan.get("color"), dict) else {"r": 1, "g": 0.2, "b": 0.2}
        return AgentAction(
            kind="set_mesh_color",
            reason=reason,
            command={
                "command": "world.set_mesh_color",
                "params": {
                    "actor_path": path,
                    "color": {
                        "r": float(color.get("r", 1)),
                        "g": float(color.get("g", 1)),
                        "b": float(color.get("b", 1)),
                        "a": 1.0,
                    },
                },
            },
        )

    if action in ("set_light", "light_props"):
        path = str(plan.get("actor_path") or "")
        if path not in snapshot.actor_paths or "PointLight" not in path:
            return AgentAction(
                kind="noop",
                reason=f"Rejected set_light — need listed PointLight: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        color = plan.get("color") if isinstance(plan.get("color"), dict) else {"r": 1, "g": 1, "b": 1}
        return AgentAction(
            kind="set_light",
            reason=reason,
            command={
                "command": "world.set_light",
                "params": {
                    "actor_path": path,
                    "intensity": float(plan.get("intensity", 8000.0)),
                    "attenuation_radius": float(plan.get("attenuation_radius", 1200.0)),
                    "color": {
                        "r": float(color.get("r", 1)),
                        "g": float(color.get("g", 1)),
                        "b": float(color.get("b", 1)),
                        "a": 1.0,
                    },
                },
            },
        )

    if action in ("destroy", "destroy_actor"):
        path = str(plan.get("actor_path") or "")
        if path not in snapshot.actor_paths:
            return AgentAction(
                kind="noop",
                reason=f"Rejected destroy — path not in outliner: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        if not any(tag in path for tag in ("PointLight", "SpotLight", "StaticMeshActor")):
            return AgentAction(
                kind="noop",
                reason=f"Rejected destroy — unsafe actor type: {path}",
                command={"command": "world.list_actors", "params": {}},
            )
        return AgentAction(
            kind="destroy",
            reason=reason,
            command={"command": "world.destroy_actor", "params": {"actor_path": path}},
        )

    return AgentAction(
        kind="noop",
        reason=reason,
        command={"command": "world.list_actors", "params": {}},
    )


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _model_supports_direct_images(model: str) -> bool:
    name = model.lower()
    return "nemotron" not in name and "deepseek" not in name


def _resolve_attach_images(model: str, attach_images: Optional[bool]) -> bool:
    if attach_images is not None:
        return attach_images
    if _env_truthy("HEPHAESTUS_PLANNER_VISION") and _model_supports_direct_images(model):
        return True
    return _model_supports_direct_images(model)


def _vision_caption_enabled() -> bool:
    return _env_truthy("HEPHAESTUS_PLANNER_VISION")


class VisionLLMPlanner:
    """NIM text planner (DeepSeek V4 Pro by default) with heuristic fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
        goal: str = "Seed a lit test scene with a few cubes, then idle.",
        fallback_rng: Optional[random.Random] = None,
        asset_hints: Optional[list[str]] = None,
        attach_images: Optional[bool] = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("HEPHAESTUS_LLM_URL")
            or DEFAULT_NIM_URL
        ).rstrip("/")
        nim_key = os.environ.get("HEPHAESTUS_LLM_API_KEY") or os.environ.get("NVIDIA_API_KEY") or ""
        openai_key = os.environ.get("OPENAI_API_KEY") or ""
        if api_key:
            self.api_key = api_key
        elif "nvidia.com" in self.base_url:
            # Do not silently send OpenAI keys to NIM
            self.api_key = nim_key
        else:
            self.api_key = nim_key or openai_key
        self.model = model or os.environ.get("HEPHAESTUS_LLM_MODEL") or DEFAULT_NEMOTRON_MODEL
        self.timeout = timeout
        self.goal = goal
        self.asset_hints = list(asset_hints or [])
        self.fallback_rng = fallback_rng or random.Random()
        self.last_raw: str = ""
        self.last_error: str = ""
        self.last_vision_caption: str = ""
        self.attach_images = _resolve_attach_images(self.model, attach_images)
        self.vision_model = (
            os.environ.get("HEPHAESTUS_VISION_MODEL", "").strip() or DEFAULT_VISION_MODEL
        )

    @property
    def available(self) -> bool:
        if self.base_url.startswith("http://127.0.0.1") or self.base_url.startswith("http://localhost"):
            return True
        return bool(self.api_key)

    def decide(
        self,
        snapshot: WorldSnapshot,
        memory: Optional[list[dict[str, Any]]] = None,
    ) -> AgentAction:
        try:
            plan = self._ask(snapshot, memory or [])
            action = plan_dict_to_action(plan, snapshot)
            action.reason = f"[{self.model}] {action.reason}"
            return action
        except Exception as exc:
            self.last_error = str(exc)
            if not self.available:
                fallback = decide_action(
                    snapshot, self.fallback_rng, goal=self.goal, asset_hints=self.asset_hints,
                )
                fallback.reason = f"[heuristic — no API key] {fallback.reason}"
                return fallback
            return AgentAction(
                kind="llm_error",
                reason=f"DeepSeek planner failed: {exc}",
                command={"command": "world.list_actors", "params": {}},
            )

    def _caption_viewport(self, snapshot: WorldSnapshot) -> str:
        """Summarize viewport JPEG via multimodal NIM when text-only planner is active."""
        if not _vision_caption_enabled() or not snapshot.frame_png or not self.api_key:
            return ""
        b64 = base64.b64encode(snapshot.frame_png).decode("ascii")
        prompt = (
            "Describe this Unreal Engine viewport in 2-3 sentences for an embodied agent. "
            "Mention visible actors, lighting, colors, and where empty space is in front of the camera."
        )
        payload = {
            "model": self.vision_model,
            "temperature": 0.1,
            "max_tokens": 180,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 45.0)) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            raw = body["choices"][0]["message"]["content"]
            if isinstance(raw, list):
                raw = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in raw
                )
            caption = str(raw).strip()
            self.last_vision_caption = caption
            return caption
        except Exception as exc:
            self.last_vision_caption = ""
            self.last_error = f"Vision caption failed: {exc}"
            return ""

    def _ask(self, snapshot: WorldSnapshot, memory: list[dict[str, Any]]) -> dict[str, Any]:
        interesting = [
            p
            for p in snapshot.actor_paths
            if any(t in p for t in (
                "PointLight", "SpotLight", "StaticMeshActor", "SkeletalMeshActor",
                "Character", "SimAgent", "Cube", "RectLight",
            ))
        ][:40]
        mem_lines = []
        for item in memory[-8:]:
            mem_lines.append(
                f"- step {item.get('step')}: {item.get('kind')} -> ok={item.get('ok')} | {item.get('reason', '')[:160]}"
            )
        vision_caption = self._caption_viewport(snapshot)
        user_text = (
            f"Goal: {self.goal}\n"
            + (
                f"Viewport vision summary: {vision_caption}\n"
                if vision_caption
                else ""
            )
            + f"Frame: {snapshot.frame_meta.get('width')}x{snapshot.frame_meta.get('height')} "
            f"({snapshot.frame_bytes} bytes) path={snapshot.frame_meta.get('path', '')}\n"
            f"Census: lights={snapshot.lights}, meshes={snapshot.meshes}, skeletal={getattr(snapshot, 'skeletal', 0)}, actors={len(snapshot.actor_paths)}\n"
            f"Pawn state: {json.dumps(snapshot.pawn_state) if getattr(snapshot, 'pawn_state', None) else '(no possessed pawn)'}\n"
            f"Camera view JSON: {json.dumps(snapshot.view) if snapshot.view else '(unknown — use x=0,y=0,z=150 as last resort)'}\n"
            f"Memory:\n" + ("\n".join(mem_lines) if mem_lines else "(none)") + "\n"
            f"Interesting actors:\n" + "\n".join(interesting[:30]) + "\n"
            f"Actor details (get_actor):\n"
            + (
                "\n".join(json.dumps(d) for d in (snapshot.actor_details or [])[:6])
                if getattr(snapshot, "actor_details", None)
                else "(none)"
            )
            + "\n"
            + (
                "Project asset hints (use mesh_path or spawn_character with these paths):\n"
                + "\n".join(f"- {p}" for p in self.asset_hints[:12])
                + "\n"
                if self.asset_hints
                else ""
            )
            + "Respond with a single JSON object only. Spawn/move INTO the camera frustum."
        )

        content: Any
        if self.attach_images and snapshot.frame_png:
            b64 = base64.b64encode(snapshot.frame_png).decode("ascii")
            content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]
        else:
            content = user_text

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": _system_prompt_for_goal(self.goal)},
                {"role": "user", "content": content},
            ],
        }
        template_kwargs = chat_template_kwargs_for_model(self.model)
        if template_kwargs:
            payload["chat_template_kwargs"] = template_kwargs

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {err[:400]}") from exc

        raw = body["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in raw
            )
        self.last_raw = str(raw)
        return _extract_json_object(self.last_raw)


def resolve_planner_mode(mode: str) -> str:
    mode = (mode or "auto").strip().lower()
    if mode in ("heuristic", "llm", "auto"):
        return mode
    raise ValueError(f"Unknown planner mode: {mode}")
