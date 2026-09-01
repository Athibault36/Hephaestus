# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Observe → decide → act → recapture loop against the Hephaestus Remote API.

v1 uses a deterministic heuristic (no LLM required) so the loop works offline
whenever PIE is listening on :8765.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from goal_grader import GradeResult, grade_goal


ThoughtFn = Callable[[str, str, dict[str, Any]], None]
AvatarFn = Callable[[str, Optional[int], Optional[str]], None]  # state, form, trigger


@dataclass
class WorldSnapshot:
    actor_paths: list[str] = field(default_factory=list)
    actor_details: list[dict[str, Any]] = field(default_factory=list)
    lights: int = 0
    meshes: int = 0
    skeletal: int = 0
    frame_meta: dict[str, Any] = field(default_factory=dict)
    frame_bytes: int = 0
    frame_png: bytes = b""
    view: dict[str, Any] = field(default_factory=dict)
    pawn_state: dict[str, Any] = field(default_factory=dict)


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
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        timeout: float = 60.0,
        retries: int = 2,
        retry_delay: float = 0.25,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(int(retries), 0)
        self.retry_delay = max(float(retry_delay), 0.0)

    def health(self) -> dict[str, Any]:
        return self._get_json("/v1/health")

    def command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/v1/command", payload)

    def frame(self) -> bytes:
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.base_url + "/v1/frame", method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay)
        raise RuntimeError(f"frame fetch failed after {self.retries + 1} attempts: {last_exc}")

    def _get_json(self, path: str) -> dict[str, Any]:
        return self._request_json("GET", path)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        return self._request_json("POST", path, data=data)

    def _request_json(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
    ) -> dict[str, Any]:
        last_error: Optional[dict[str, Any]] = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(
                    self.base_url + path,
                    data=data,
                    headers={"Content-Type": "application/json"} if data else {},
                    method=method,
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = {
                    "success": False,
                    "error": f"HTTP {exc.code}: {body[:400]}",
                    "http_status": exc.code,
                    "result_json": "{}",
                }
                if exc.code >= 500 and attempt < self.retries:
                    time.sleep(self.retry_delay)
                    continue
                return last_error
            except Exception as exc:
                last_error = {
                    "success": False,
                    "error": str(exc),
                    "result_json": "{}",
                }
                if attempt < self.retries:
                    time.sleep(self.retry_delay)
                    continue
        return last_error or {"success": False, "error": "unknown", "result_json": "{}"}


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


def summarize_actors(paths: list[str]) -> tuple[int, int, int]:
    lights = sum(1 for p in paths if "PointLight" in p or "SpotLight" in p or "RectLight" in p)
    meshes = sum(1 for p in paths if "StaticMeshActor" in p)
    skel = sum(
        1
        for p in paths
        if any(tag in p for tag in ("SkeletalMeshActor", "SimAgentCharacter", "Character"))
    )
    return lights, meshes, skel


def _camera_spawn_xyz(view: dict[str, Any], rng: random.Random, dist: float = 450.0) -> tuple[float, float, float]:
    loc = view.get("location") or {"x": 0.0, "y": 0.0, "z": 200.0}
    fwd = view.get("forward") or {"x": 1.0, "y": 0.0, "z": 0.0}
    d = dist + float(rng.randint(0, 150))
    side = float(rng.randint(-80, 80))
    x = float(loc.get("x", 0)) + float(fwd.get("x", 1)) * d - float(fwd.get("y", 0)) * side
    y = float(loc.get("y", 0)) + float(fwd.get("y", 0)) * d + float(fwd.get("x", 1)) * side
    z = float(loc.get("z", 100)) + float(fwd.get("z", 0)) * d - 40.0
    return x, y, max(z, 50.0)


def _pick_asset_path(goal: str, asset_hints: Optional[list[str]]) -> Optional[str]:
    paths = list(asset_hints or [])
    paths.extend(re.findall(r"/Game/[^\s,;\"']+", goal or ""))
    seen: set[str] = set()
    ordered: list[str] = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered[0] if ordered else None


from locomotion_fallback import infer_locomotion_mode


def _pick_actor_path_from_goal(goal: str, snapshot: WorldSnapshot) -> Optional[str]:
    for match in re.findall(r"/Temp/[^\s,;\"']+", goal or ""):
        for path in snapshot.actor_paths:
            if match in path or path.endswith(match.split(".")[-1]):
                return path
        return match
    return None


def _pick_skeletal_path(snapshot: WorldSnapshot, goal: str = "") -> Optional[str]:
    from_goal = _pick_actor_path_from_goal(goal, snapshot)
    if from_goal:
        return from_goal
    return _pick_skeletal_path_from_snapshot(snapshot)


def _pick_skeletal_path_from_snapshot(snapshot: WorldSnapshot) -> Optional[str]:
    for path in snapshot.actor_paths:
        if any(tag in path for tag in ("SkeletalMeshActor", "SimAgentCharacter", "Character")):
            return path
    return None


def _pick_anim_path(goal: str, asset_hints: Optional[list[str]]) -> Optional[str]:
    goal_l = (goal or "").lower()
    want: list[str] = []
    if "run" in goal_l:
        want.append("run")
    if "walk" in goal_l:
        want.append("walk")
    if "idle" in goal_l:
        want.append("idle")
    if not want:
        return None
    hints = list(asset_hints or [])
    for token in want:
        for path in hints:
            blob = path.lower()
            if token in blob and ("anim" in blob or "montage" in blob):
                return path
    return None


def _creature_keywords(goal: str) -> list[str]:
    words = ("dog", "cat", "wolf", "horse", "bird", "creature", "dragon", "fox", "character")
    goal_l = (goal or "").lower()
    return [w for w in words if w in goal_l]


def _pick_creature_spawn(goal: str, asset_hints: Optional[list[str]]) -> Optional[str]:
    if not _creature_keywords(goal):
        return None
    hints = list(asset_hints or [])
    creatures = _creature_keywords(goal)
    for path in hints:
        blob = path.lower()
        if any(c in blob for c in creatures) and (
            "skeletalmesh" in blob or "/sk_" in blob or path.endswith(".skeletalmesh")
        ):
            return path
    for path in hints:
        if "SkeletalMesh" in path or "/SK_" in path:
            return path
    return None


def decide_action(
    snapshot: WorldSnapshot,
    rng: random.Random,
    goal: str = "",
    asset_hints: Optional[list[str]] = None,
) -> AgentAction:
    """Heuristic policy: seed light + cubes, or spawn named /Game asset in view."""
    view = snapshot.view or {}
    x, y, z = _camera_spawn_xyz(view, rng)
    asset_path = _pick_asset_path(goal, asset_hints)
    creature_mesh = _pick_creature_spawn(goal, asset_hints)
    if creature_mesh and snapshot.skeletal < 1 and snapshot.lights >= 1:
        return AgentAction(
            kind="spawn_creature",
            reason=f"Heuristic spawn creature mesh {creature_mesh} in view",
            command={
                "command": "animation.spawn_character",
                "params": {
                    "mesh_path": creature_mesh,
                    "transform": {
                        "location": {"x": x, "y": y, "z": z},
                        "rotation": {"pitch": 0.0, "yaw": float(rng.randint(0, 45)), "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            },
        )

    if asset_path and snapshot.lights < 1:
        return AgentAction(
            kind="spawn_light",
            reason=f"Lighting scene before spawning {asset_path}",
            command={
                "command": "world.spawn_actor",
                "params": {
                    "class_path": "/Script/Engine.PointLight",
                    "transform": {
                        "location": {"x": x, "y": y, "z": z + 120.0},
                        "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            },
        )

    if asset_path:
        skel = (
            "SkeletalMesh" in asset_path
            or asset_path.endswith(".SkeletalMesh")
            or "/SK_" in asset_path
        )
        if skel and snapshot.skeletal < 1:
            use_character = any(
                w in (goal or "").lower() for w in ("jog", "walk", "run", "gameplay", "character")
            )
            return AgentAction(
                kind="spawn_character" if use_character else "spawn_skeletal",
                reason=f"Heuristic spawn skeletal {asset_path} in view",
                command={
                    "command": "animation.spawn_character" if use_character else "animation.spawn_skeletal_mesh",
                    "params": {
                        "mesh_path": asset_path,
                        "transform": {
                            "location": {"x": x, "y": y, "z": z},
                            "rotation": {"pitch": 0.0, "yaw": float(rng.randint(0, 45)), "roll": 0.0},
                            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                        },
                    },
                },
            )
        if not skel and snapshot.meshes < 1:
            return AgentAction(
                kind="spawn_cube",
                reason=f"Heuristic spawn mesh {asset_path} in view",
                command={
                    "command": "world.spawn_mesh",
                    "params": {
                        "mesh_path": asset_path,
                        "transform": {
                            "location": {"x": x, "y": y, "z": z},
                            "rotation": {"pitch": 0.0, "yaw": float(rng.randint(0, 45)), "roll": 0.0},
                            "scale": {"x": 2.0, "y": 2.0, "z": 2.0},
                        },
                    },
                },
            )

    goal_l = (goal or "").lower()
    skel_path = _pick_skeletal_path(snapshot, goal)
    anim_path = _pick_anim_path(goal, asset_hints)
    locomotion_mode = infer_locomotion_mode(goal)
    if skel_path and locomotion_mode and not anim_path:
        return AgentAction(
            kind="play_locomotion",
            reason=f"Heuristic locomotion {locomotion_mode} on {skel_path}",
            command={
                "command": "animation.play_locomotion",
                "params": {"actor_path": skel_path, "mode": locomotion_mode, "loop": True},
            },
        )
    if skel_path and anim_path and any(w in goal_l for w in ("walk", "run", "idle", "anim", "playing")):
        if "montage" in anim_path.lower():
            return AgentAction(
                kind="play_montage",
                reason=f"Heuristic play montage {anim_path} on {skel_path}",
                command={
                    "command": "animation.play_montage",
                    "params": {"actor_path": skel_path, "montage_path": anim_path, "loop": True},
                },
            )
        return AgentAction(
            kind="play_anim",
            reason=f"Heuristic play anim {anim_path} on {skel_path}",
            command={
                "command": "animation.play_sequence",
                "params": {"actor_path": skel_path, "anim_path": anim_path, "loop": True},
            },
        )

    if snapshot.lights < 1:
        return AgentAction(
            kind="spawn_light",
            reason=f"No lights yet (meshes={snapshot.meshes}). Seed a PointLight in view.",
            command={
                "command": "world.spawn_actor",
                "params": {
                    "class_path": "/Script/Engine.PointLight",
                    "transform": {
                        "location": {"x": x, "y": y, "z": z + 120.0},
                        "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                },
            },
        )

    if snapshot.meshes < 3:
        return AgentAction(
            kind="spawn_cube",
            reason=f"lights={snapshot.lights} meshes={snapshot.meshes}. Seed/add a cube in view.",
            command={
                "command": "world.spawn_mesh",
                "params": {
                    "mesh_path": "/Engine/BasicShapes/Cube.Cube",
                    "transform": {
                        "location": {"x": x, "y": y, "z": max(z, 50.0)},
                        "rotation": {"pitch": 0.0, "yaw": float(rng.randint(0, 45)), "roll": 0.0},
                        "scale": {"x": 2.0, "y": 2.0, "z": 2.0},
                    },
                },
            },
        )

    if any(w in goal_l for w in ("jog", "run forward", "walk forward", "move forward")):
        skel_for_move = _pick_skeletal_path(snapshot, goal)
        anim_live = any(
            bool(d.get("anim_playing"))
            for d in (snapshot.actor_details or [])
            if isinstance(d, dict)
        )
        if skel_for_move and not anim_live and any(w in goal_l for w in ("walk", "jog", "run")):
            mode = "run" if "run" in goal_l else "walk"
            return AgentAction(
                kind="play_locomotion",
                reason=f"Heuristic {mode} anim before pawn move",
                command={
                    "command": "animation.play_locomotion",
                    "params": {"actor_path": skel_for_move, "mode": mode, "loop": True},
                },
            )
        return AgentAction(
            kind="apply_move",
            reason="Heuristic jog forward toward gameplay goal",
            command={
                "command": "world.apply_move_input",
                "params": {"forward": 1.0, "right": 0.0, "duration": 3.0},
            },
        )

    if any(w in goal_l for w in ("frame", "shot", "cinematic")) or (
        "camera" in goal_l and any(w in goal_l for w in ("left", "right", "from"))
    ):
        loc = view.get("location") or {"x": 0.0, "y": 0.0, "z": 200.0}
        fwd = view.get("forward") or {"x": 1.0, "y": 0.0, "z": 0.0}
        side = 250.0 if "left" in goal_l else (-250.0 if "right" in goal_l else 0.0)
        cam_x = float(loc.get("x", 0)) + float(fwd.get("x", 1)) * 200.0 - float(fwd.get("y", 0)) * side
        cam_y = float(loc.get("y", 0)) + float(fwd.get("y", 0)) * 200.0 + float(fwd.get("x", 1)) * side
        cam_z = float(loc.get("z", 200)) + 40.0
        yaw = float(rng.randint(-30, 30))
        if "left" in goal_l:
            yaw = -45.0
        elif "right" in goal_l:
            yaw = 45.0
        skel_frame = _pick_skeletal_path(snapshot, goal)
        shot_params: dict[str, Any] = {
            "location": {"x": cam_x, "y": cam_y, "z": cam_z},
            "rotation": {"pitch": -10.0, "yaw": yaw, "roll": 0.0},
            "duration": 3.0,
            "ease_in_out": True,
        }
        if skel_frame:
            shot_params["look_at_actor"] = skel_frame
        return AgentAction(
            kind="create_shot",
            reason="Heuristic cinematic camera shot for framing goal",
            command={
                "command": "sequence.create_shot",
                "params": shot_params,
            },
        )

    return AgentAction(
        kind="noop",
        reason=f"Level seeded (lights={snapshot.lights}, meshes={snapshot.meshes}). Holding.",
        command={"command": "world.list_actors", "params": {}},
    )


def _maybe_repair_command(
    command: dict[str, Any],
    snapshot: WorldSnapshot,
    goal: str,
    error: str,
) -> Optional[dict[str, Any]]:
    err = (error or "").lower()
    params = dict(command.get("params") or {})
    repaired = dict(command)
    if "actor_path" in err and not params.get("actor_path"):
        skel = _pick_skeletal_path(snapshot, goal)
        if skel:
            params["actor_path"] = skel
            repaired["params"] = params
            return repaired
    if command.get("command") == "animation.play_locomotion" and not params.get("mode"):
        mode = infer_locomotion_mode(goal)
        if mode:
            params["mode"] = mode
            repaired["params"] = params
            return repaired
    if command.get("command") == "audio.create_metasound" and not params.get("source_path"):
        paths = re.findall(r"/Game/[^\s,;\"']+", goal or "")
        if paths:
            params["source_path"] = paths[-1]
            repaired["params"] = params
            return repaired
    return None


class ObserveActLoop:
    def __init__(
        self,
        client: Optional[RemoteUeClient] = None,
        seed: Optional[int] = None,
        on_thought: Optional[ThoughtFn] = None,
        on_avatar: Optional[AvatarFn] = None,
        planner: Optional[Callable[..., AgentAction]] = None,
        goal: str = "",
        asset_hints: Optional[list[str]] = None,
    ):
        self.client = client or RemoteUeClient()
        self.rng = random.Random(seed)
        self.on_thought = on_thought or (lambda *_args: None)
        self.on_avatar = on_avatar or (lambda *args, **kwargs: None)
        self.planner = planner
        self.goal = goal
        self.asset_hints = list(asset_hints or [])
        self.memory: list[dict[str, Any]] = []
        self._observe_count = 0

    def _avatar(self, state: str, form: Optional[int] = None, trigger: Optional[str] = None) -> None:
        """Emit avatar state change."""
        self.on_avatar(state, form, trigger)

    def _decide(self, snapshot: WorldSnapshot) -> AgentAction:
        if self.planner is not None:
            try:
                action = self.planner(snapshot, self.memory)
            except TypeError:
                action = self.planner(snapshot)
            if action.kind == "llm_error":
                fallback = decide_action(
                    snapshot, self.rng, goal=self.goal, asset_hints=self.asset_hints,
                )
                fallback.reason = f"{action.reason} → continuing: {fallback.reason}"
                self._thought("error", action.reason, {"kind": "llm_error"})
                return fallback
            return action
        return decide_action(snapshot, self.rng, goal=self.goal, asset_hints=self.asset_hints)

    def _thought(self, kind: str, content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        self.on_thought(kind, content, metadata or {})
        # Map thought kinds to avatar states
        if kind == "observation":
            self._avatar("thinking", None, "observing")
        elif kind == "plan":
            self._avatar("thinking", None, "planning")
        elif kind == "action":
            self._avatar("working", None, "acting")
        elif kind == "tool_result":
            self._avatar("success", None, "result_ok")
        elif kind == "error":
            self._avatar("error", None, "result_error")
        elif kind == "reflection":
            self._avatar("thinking", None, "reflecting")

    def observe(self) -> WorldSnapshot:
        self._observe_count += 1
        if self._observe_count % 4 == 1 and self.goal:
            try:
                from agent_asset import augment_goal_with_assets

                _, matches, _meta = augment_goal_with_assets(self.client, self.goal)
                if matches:
                    self.asset_hints = matches
            except Exception:
                pass
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

        listed = self.client.command({
            "command": "world.list_actors",
            "params": {"include_details": True, "detail_limit": 12},
        })
        paths = _parse_actor_paths(listed)
        lights, meshes, skeletal = summarize_actors(paths)
        actor_details: list[dict[str, Any]] = []
        inner = _parse_result_json(listed)
        raw_details = inner.get("actor_details") or []
        if isinstance(raw_details, list):
            for item in raw_details:
                if isinstance(item, dict):
                    actor_details.append(item)
        if not actor_details:
            for path in paths:
                if not any(
                    tag in path
                    for tag in (
                        "PointLight",
                        "StaticMeshActor",
                        "SkeletalMeshActor",
                        "SpotLight",
                        "SimAgentCharacter",
                        "Character",
                    )
                ):
                    continue
                if len(actor_details) >= 10:
                    break
                detail_res = self.client.command(
                    {"command": "world.get_actor", "params": {"actor_path": path}}
                )
                if detail_res.get("success"):
                    detail = _parse_result_json(detail_res)
                    if detail:
                        actor_details.append(detail)
        view = {}
        view_res = self.client.command({"command": "world.get_view", "params": {}})
        if view_res.get("success"):
            view = _parse_result_json(view_res)
        pawn_state: dict[str, Any] = {}
        pawn_res = self.client.command({"command": "world.get_pawn_state", "params": {}})
        if pawn_res.get("success"):
            pawn_state = _parse_result_json(pawn_res)
        snap = WorldSnapshot(
            actor_paths=paths,
            actor_details=actor_details,
            lights=lights,
            meshes=meshes,
            skeletal=skeletal,
            frame_meta=meta,
            frame_bytes=frame_bytes,
            frame_png=frame,
            view=view,
            pawn_state=pawn_state,
        )
        self._thought(
            "observation",
            f"Frame {meta.get('width')}x{meta.get('height')} ({frame_bytes} bytes); "
            f"actors={len(paths)} lights={lights} meshes={meshes} skeletal={skeletal}"
            + (f"; view=({view.get('location', {})})" if view else "")
            + (f"; pawn_speed={pawn_state.get('speed', 0)}" if pawn_state else ""),
            {"frame": meta, "lights": lights, "meshes": meshes, "view": view, "pawn": pawn_state},
        )
        return snap

    def step(self, step_index: int = 1) -> StepResult:
        self._avatar("thinking", None, f"step_{step_index}_start")
        before = self.observe()
        action = self._decide(before)
        self._thought("plan", action.reason, {"kind": action.kind})
        self._thought("action", f"Executing {action.command.get('command')}", action.command)

        if action.kind == "noop":
            act_result = {"success": True, "error": "", "result_json": "{}", "skipped": True}
        else:
            self._avatar("working", None, f"executing_{action.kind}")
            act_result = self.client.command(action.command)
            if not act_result.get("success"):
                repaired = _maybe_repair_command(
                    action.command,
                    before,
                    self.goal,
                    str(act_result.get("error") or ""),
                )
                if repaired:
                    self._thought("plan", "Repairing command params and retrying once", repaired)
                    act_result = self.client.command(repaired)
                    action.command = repaired

        ok = bool(act_result.get("success", False))
        self._thought(
            "tool_result" if ok else "error",
            f"{action.kind}: {'ok' if ok else act_result.get('error')}",
            act_result,
        )

        mem_entry: dict[str, Any] = {
                "step": step_index,
                "kind": action.kind,
                "reason": action.reason,
                "ok": ok,
                "command": action.command.get("command"),
                "actor_path": (action.command.get("params") or {}).get("actor_path"),
                "lights_before": before.lights,
                "meshes_before": before.meshes,
                "mesh_path": (action.command.get("params") or {}).get("mesh_path"),
            }
        if ok and action.command.get("command") == "sequence.create_shot":
            inner = _parse_result_json(act_result)
            if inner.get("shot_path") or inner.get("sequence_path"):
                mem_entry["shot_path"] = inner.get("shot_path") or inner.get("sequence_path")
        self.memory.append(mem_entry)

        time.sleep(
            min(
                max(
                    float((action.command.get("params") or {}).get("duration", 0.15)) * 0.5,
                    0.25,
                ),
                3.0,
            )
            if action.kind in ("apply_move", "create_shot", "move_actor")
            else 0.15
        )
        after = self.observe()
        self._avatar("thinking", None, f"step_{step_index}_reobserving")
        return StepResult(
            step=step_index,
            observation=before,
            action=action,
            act_result=act_result,
            reobservation=after,
            ok=ok,
        )

    def run(self, steps: int = 3, max_steps: Optional[int] = None) -> list[StepResult]:
        self.client.health()
        if self.goal:
            self._thought("plan", f"Goal: {self.goal}")
        self._avatar("connecting", None, "initializing")
        self._avatar("working", None, "loop_start")
        budget = max_steps if max_steps is not None else steps
        results: list[StepResult] = []
        for i in range(1, budget + 1):
            self._thought("plan", f"Agent step {i}/{budget}")
            self._avatar("thinking", None, f"step_{i}_planning")
            results.append(self.step(i))
            grade = grade_goal(self.goal, results[-1].reobservation, self.memory)
            self._thought(
                "reflection",
                grade.summary,
                {"met": grade.met, "score": grade.score, "missing": grade.missing},
            )
            if grade.met:
                self._avatar("success", None, "goal_satisfied")
                break
            if results[-1].action.kind == "noop" and results[-1].ok and grade.met:
                break
        final_state = "success" if results and all(r.ok for r in results) else "error"
        if results and grade_goal(self.goal, results[-1].reobservation, self.memory).met:
            final_state = "success"
        self._avatar(final_state, None, "loop_end")
        self._avatar("active" if final_state == "success" else "idle", None, "return_idle")
        return results

    def run_until_goal(self, max_steps: int = 20) -> tuple[list[StepResult], GradeResult]:
        """Run observe-act until goal grader passes or max_steps exhausted."""
        budget = max(max_steps, 8)
        results = self.run(steps=budget, max_steps=budget)
        grade = grade_goal(
            self.goal,
            results[-1].reobservation if results else WorldSnapshot(),
            self.memory,
        )
        extensions = 0
        while not grade.met and extensions < 2 and results:
            last = results[-1]
            progressed = (
                last.reobservation.lights > last.observation.lights
                or last.reobservation.meshes > last.observation.meshes
                or last.reobservation.skeletal > last.observation.skeletal
                or any(s.get("ok") for s in self.memory[-3:])
            )
            if not progressed:
                break
            extensions += 1
            extra = self.run(steps=8, max_steps=8)
            results.extend(extra)
            grade = grade_goal(self.goal, results[-1].reobservation, self.memory)
        return results, grade
