# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Nemotron-3 planner for the UE observe→act loop (NVIDIA NIM OpenAI-compatible API).

Default model: nvidia/nemotron-3-ultra @ https://integrate.api.nvidia.com/v1
Auth: NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY

Nemotron is used as a text planner over frame census + step memory (multimodal
image parts are omitted for nemotron* models).
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

DEFAULT_NIM_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra"

SYSTEM_PROMPT = """You are HEPHAESTUS, an embodied Unreal Engine agent controlled by Nemotron-3.
You receive a viewport census (and optional prior step memory). Choose exactly ONE next action.

Allowed JSON (no markdown):
{
  "action": "spawn_light" | "spawn_cube" | "set_transform" | "set_light" | "destroy" | "noop",
  "reason": "short why",
  "x": number, "y": number, "z": number,
  "yaw": number,
  "actor_path": "required for set_transform/set_light/destroy",
  "intensity": number,
  "color": {"r":0-1,"g":0-1,"b":0-1},
  "attenuation_radius": number,
  "class_path": "only PointLight|SpotLight|StaticMeshActor allowlisted paths"
}

Rules:
- Prefer small reversible edits. |x|,|y| <= 400 unless memory says otherwise.
- destroy/set_* only with actor_path from the provided interesting-actor list.
- set_light only on PointLight paths.
- noop when goal is met (e.g. >=1 light and >=3 cubes for a basic seed goal).
- Use memory so you do not repeat the same failed or redundant spawn.
"""


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


def plan_dict_to_action(plan: dict[str, Any], snapshot: WorldSnapshot) -> AgentAction:
    """Validate planner JSON into a Remote API command."""
    action = str(plan.get("action") or plan.get("kind") or "noop").strip().lower()
    reason = str(plan.get("reason") or "LLM plan")
    x = float(plan.get("x", 0.0))
    y = float(plan.get("y", 0.0))
    z = float(plan.get("z", 200.0))
    yaw = float(plan.get("yaw", 0.0))

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
        return AgentAction(
            kind="spawn_cube",
            reason=reason,
            command={
                "command": "world.spawn_mesh",
                "params": {
                    "mesh_path": "/Engine/BasicShapes/Cube.Cube",
                    "transform": transform(z if z else 100.0),
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


class VisionLLMPlanner:
    """Nemotron-3 (NIM) text planner with heuristic fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
        goal: str = "Seed a lit test scene with a few cubes, then idle.",
        fallback_rng: Optional[random.Random] = None,
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
        self.fallback_rng = fallback_rng or random.Random()
        self.last_raw: str = ""
        self.last_error: str = ""
        # Nemotron chat is text-first; only attach images for explicitly multimodal models
        if attach_images is None:
            self.attach_images = "nemotron" not in self.model.lower()
        else:
            self.attach_images = attach_images

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
            action.reason = f"[nemotron/{self.model}] {action.reason}"
            return action
        except Exception as exc:
            self.last_error = str(exc)
            fallback = decide_action(snapshot, self.fallback_rng)
            fallback.reason = f"[heuristic fallback after LLM error: {exc}] {fallback.reason}"
            return fallback

    def _ask(self, snapshot: WorldSnapshot, memory: list[dict[str, Any]]) -> dict[str, Any]:
        interesting = [
            p
            for p in snapshot.actor_paths
            if any(t in p for t in ("PointLight", "SpotLight", "StaticMeshActor", "Cube", "RectLight"))
        ][:40]
        mem_lines = []
        for item in memory[-8:]:
            mem_lines.append(
                f"- step {item.get('step')}: {item.get('kind')} -> ok={item.get('ok')} | {item.get('reason', '')[:160]}"
            )
        user_text = (
            f"Goal: {self.goal}\n"
            f"Frame: {snapshot.frame_meta.get('width')}x{snapshot.frame_meta.get('height')} "
            f"({snapshot.frame_bytes} bytes) path={snapshot.frame_meta.get('path', '')}\n"
            f"Census: lights={snapshot.lights}, meshes={snapshot.meshes}, actors={len(snapshot.actor_paths)}\n"
            f"Memory:\n" + ("\n".join(mem_lines) if mem_lines else "(none)") + "\n"
            f"Interesting actors:\n" + "\n".join(interesting[:30]) + "\n"
            "Respond with a single JSON object only."
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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        }

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
