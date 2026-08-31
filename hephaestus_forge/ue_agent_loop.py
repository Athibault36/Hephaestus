# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Observe → decide → act → recapture loop against the Hephaestus Remote API.

v1 uses a deterministic heuristic (no LLM required) so the loop works offline
whenever PIE is listening on :8765.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


ThoughtFn = Callable[[str, str, dict[str, Any]], None]


@dataclass
class WorldSnapshot:
    actor_paths: list[str] = field(default_factory=list)
    lights: int = 0
    meshes: int = 0
    frame_meta: dict[str, Any] = field(default_factory=dict)
    frame_bytes: int = 0
    frame_png: bytes = b""


@dataclass
class AgentAction:
    kind: str
    reason: str
    command: dict[str, Any]


@dataclass
class StepResult:
    step: int
    observation: WorldSnapshot
    action: AgentAction
    act_result: dict[str, Any]
    reobservation: WorldSnapshot
    ok: bool


class RemoteUeClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._get_json("/v1/health")

    def command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/v1/command", payload)

    def frame(self) -> bytes:
        req = urllib.request.Request(self.base_url + "/v1/frame", method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def _get_json(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + path, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


def _parse_actor_paths(result: dict[str, Any]) -> list[str]:
    paths = list(result.get("actor_paths") or [])
    raw = result.get("result_json") or "{}"
    try:
        inner = json.loads(raw)
        if isinstance(inner.get("actors"), list):
            paths = [str(p) for p in inner["actors"]]
    except json.JSONDecodeError:
        pass
    return paths


def _parse_result_json(result: dict[str, Any]) -> dict[str, Any]:
    raw = result.get("result_json") or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def summarize_actors(paths: list[str]) -> tuple[int, int]:
    lights = sum(1 for p in paths if "PointLight" in p or "SpotLight" in p or "RectLight" in p)
    meshes = sum(1 for p in paths if "StaticMeshActor" in p)
    return lights, meshes


def decide_action(snapshot: WorldSnapshot, rng: random.Random) -> AgentAction:
    """Heuristic policy: seed light + cubes, then idle."""
    x = float(rng.randint(-200, 200))
    y = float(rng.randint(-200, 200))

    if snapshot.lights < 1:
        return AgentAction(
            kind="spawn_light",
            reason=f"No lights yet (meshes={snapshot.meshes}). Seed a PointLight.",
            command={
                "command": "world.spawn_actor",
                "params": {
                    "class_path": "/Script/Engine.PointLight",
                    "transform": {
                        "location": {"x": x, "y": y, "z": 280.0},
                        "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            },
        )

    if snapshot.meshes < 1:
        return AgentAction(
            kind="spawn_cube",
            reason=f"Have light(s)={snapshot.lights} but no cubes. Seed a cube.",
            command={
                "command": "world.spawn_mesh",
                "params": {
                    "mesh_path": "/Engine/BasicShapes/Cube.Cube",
                    "transform": {
                        "location": {"x": x, "y": y, "z": 100.0},
                        "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            },
        )

    if snapshot.meshes < 3:
        return AgentAction(
            kind="spawn_cube",
            reason=f"Only {snapshot.meshes} cube(s). Add another for spatial variety.",
            command={
                "command": "world.spawn_mesh",
                "params": {
                    "mesh_path": "/Engine/BasicShapes/Cube.Cube",
                    "transform": {
                        "location": {"x": x, "y": y, "z": 100.0},
                        "rotation": {"pitch": 0.0, "yaw": float(rng.randint(0, 90)), "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            },
        )

    return AgentAction(
        kind="noop",
        reason=f"Level seeded (lights={snapshot.lights}, meshes={snapshot.meshes}). Holding.",
        command={"command": "world.list_actors", "params": {}},
    )


class ObserveActLoop:
    def __init__(
        self,
        client: Optional[RemoteUeClient] = None,
        seed: Optional[int] = None,
        on_thought: Optional[ThoughtFn] = None,
        planner: Optional[Callable[..., AgentAction]] = None,
        goal: str = "",
    ):
        self.client = client or RemoteUeClient()
        self.rng = random.Random(seed)
        self.on_thought = on_thought or (lambda *_args: None)
        self.planner = planner
        self.goal = goal
        self.memory: list[dict[str, Any]] = []

    def _thought(self, kind: str, content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        self.on_thought(kind, content, metadata or {})

    def _decide(self, snapshot: WorldSnapshot) -> AgentAction:
        if self.planner is not None:
            try:
                return self.planner(snapshot, self.memory)
            except TypeError:
                return self.planner(snapshot)
        return decide_action(snapshot, self.rng)

    def observe(self) -> WorldSnapshot:
        self._thought("observation", "Capturing viewport + listing actors")
        cap = self.client.command({"command": "vision.capture_frame", "params": {}})
        if not cap.get("success"):
            raise RuntimeError(f"capture_frame failed: {cap.get('error')}")
        meta = _parse_result_json(cap)
        frame = b""
        try:
            frame = self.client.frame()
            frame_bytes = len(frame)
        except urllib.error.HTTPError:
            frame_bytes = 0

        listed = self.client.command({"command": "world.list_actors", "params": {}})
        paths = _parse_actor_paths(listed)
        lights, meshes = summarize_actors(paths)
        snap = WorldSnapshot(
            actor_paths=paths,
            lights=lights,
            meshes=meshes,
            frame_meta=meta,
            frame_bytes=frame_bytes,
            frame_png=frame,
        )
        self._thought(
            "observation",
            f"Frame {meta.get('width')}x{meta.get('height')} ({frame_bytes} bytes); "
            f"actors={len(paths)} lights={lights} meshes={meshes}",
            {"frame": meta, "lights": lights, "meshes": meshes},
        )
        return snap

    def step(self, step_index: int = 1) -> StepResult:
        before = self.observe()
        action = self._decide(before)
        self._thought("plan", action.reason, {"kind": action.kind})
        self._thought("action", f"Executing {action.command.get('command')}", action.command)

        if action.kind == "noop":
            act_result = {"success": True, "error": "", "result_json": "{}", "skipped": True}
        else:
            act_result = self.client.command(action.command)

        ok = bool(act_result.get("success", False))
        self._thought(
            "tool_result" if ok else "error",
            f"{action.kind}: {'ok' if ok else act_result.get('error')}",
            act_result,
        )

        self.memory.append(
            {
                "step": step_index,
                "kind": action.kind,
                "reason": action.reason,
                "ok": ok,
                "command": action.command.get("command"),
                "lights_before": before.lights,
                "meshes_before": before.meshes,
            }
        )

        time.sleep(0.15)
        after = self.observe()
        return StepResult(
            step=step_index,
            observation=before,
            action=action,
            act_result=act_result,
            reobservation=after,
            ok=ok,
        )

    def run(self, steps: int = 3) -> list[StepResult]:
        self.client.health()
        if self.goal:
            self._thought("plan", f"Goal: {self.goal}")
        results: list[StepResult] = []
        for i in range(1, steps + 1):
            self._thought("plan", f"Agent step {i}/{steps}")
            results.append(self.step(i))
            if results[-1].action.kind == "noop" and results[-1].ok:
                self._thought("reflection", "Goal satisfied — stopping early")
                break
        return results
