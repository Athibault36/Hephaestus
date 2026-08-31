"""Expanded fake UE bridge for integration testing."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from hephaestus_forge.runtime.config import AUTH_HEADER

AVAILABLE_COMMANDS = [
    "world.spawn_actor",
    "world.destroy_actor",
    "world.query_spatial",
    "world.batch_edit",
    "vision.capture_frame",
    "asset.create_material",
    "asset.import",
    "asset.reimport",
    "asset.export",
    "asset.create_instance",
    "blueprint.compile",
    "blueprint.add_function",
    "blueprint.set_property",
    "blueprint.diff",
    "rendering.add_pass",
    "rendering.create_shader_params",
    "rendering.dispatch_compute",
    "pcg.mutate_graph",
    "pcg.set_metadata",
    "pcg.query_spatial",
    "animation.create_control_rig",
    "animation.retarget",
    "animation.edit_sequence",
    "animation.livelink_connect",
    "audio.create_metasound",
    "audio.play_quartz",
    "audio.synthesize",
]

MAX_BODY_BYTES = 1024 * 1024


class FakeUE:
    """Records commands and produces plausible command results."""

    def __init__(self, *, require_auth: bool = False, auth_token: str = "test-token") -> None:
        self.received: List[Dict[str, Any]] = []
        self.spawn_counter = 0
        self.frame_counter = 0
        self.command_counter = 0
        self.fail_transport_times = 0
        self.require_auth = require_auth
        self.auth_token = auth_token

    PNG_1PX = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c636060606000000005000104b8b0f0000000004945"
        "4e44ae426082"
    )

    def _check_auth(self, request: httpx.Request) -> Optional[httpx.Response]:
        if not self.require_auth:
            return None
        token = request.headers.get(AUTH_HEADER)
        if token != self.auth_token:
            return httpx.Response(401, json={"success": False, "error_message": "unauthorized", "error_kind": "auth"})
        return None

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        discovery = path in ("/health", "/commands")
        auth_resp = self._check_auth(request)
        if auth_resp is not None and not discovery:
            return auth_resp

        if request.method == "GET" and path == "/health":
            return httpx.Response(200, json={"status": "ok", "commands": len(AVAILABLE_COMMANDS)})
        if request.method == "GET" and path == "/commands":
            return httpx.Response(200, json={"commands": AVAILABLE_COMMANDS})
        if request.method == "GET" and path.startswith("/frame/"):
            if self.require_auth and request.headers.get(AUTH_HEADER) != self.auth_token:
                return httpx.Response(401, json={"error": "unauthorized"})
            return httpx.Response(200, content=self.PNG_1PX, headers={"Content-Type": "image/png"})
        if request.method == "POST" and path in ("/command", "/batch"):
            if len(request.content or b"") > MAX_BODY_BYTES:
                return httpx.Response(413, json={"success": False, "error_message": "payload too large"})
            if self.fail_transport_times > 0:
                self.fail_transport_times -= 1
                return httpx.Response(503, json={"error": "warming up"})
            body = json.loads(request.content.decode() or "{}")
            if path == "/batch":
                results = [self._run(env) for env in body.get("commands", [])]
                return httpx.Response(200, json={"results": results})
            return httpx.Response(200, json=self._run(body))
        return httpx.Response(404, json={"error": f"no route {request.method} {path}"})

    def _run(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        self.received.append(envelope)
        command = envelope.get("command", "")
        params = envelope.get("params", {})
        self.command_counter += 1
        cid = f"cmd_{self.command_counter}"

        if command not in AVAILABLE_COMMANDS:
            return _err(cid, f"unknown command {command}", code="UNKNOWN_COMMAND")

        if command == "world.spawn_actor":
            if not params.get("class_path"):
                return _err(cid, "missing class_path", code="VALIDATION_MISSING_FIELD")
            self.spawn_counter += 1
            path = f"/Game/Maps/UEDPIE_0_Main.Main:PersistentLevel.SpawnedActor_{self.spawn_counter}"
            return _ok(cid, {"actor_path": path, "stub": False}, actors=[path])
        if command == "world.destroy_actor":
            return _ok(cid, {}) if params.get("actor_path") else _err(cid, "missing actor_path")
        if command == "world.query_spatial":
            return _ok(cid, {"actors": []})
        if command == "world.batch_edit":
            return _ok(cid, {"edited": len(params.get("actors") or []), "stub": True})
        if command == "vision.capture_frame":
            self.frame_counter += 1
            return _ok(cid, {"frame_id": self.frame_counter, "width": 1920, "height": 1080})
        return _ok(cid, {"command": command, "action": params.get("action", ""), "stub": True})


def _ok(cid: str, result: Dict[str, Any], actors: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "success": True,
        "error_message": "",
        "result_json": json.dumps(result),
        "actor_references": actors or [],
        "asset_references": result.get("asset_path", []) if isinstance(result.get("asset_path"), list) else [],
        "execution_time_ms": 0.5,
        "command_id": cid,
    }


def _err(cid: str, message: str, code: str = "COMMAND_FAILED") -> Dict[str, Any]:
    return {
        "success": False,
        "error_message": message,
        "error_kind": "command",
        "error_code": code,
        "result_json": "{}",
        "actor_references": [],
        "asset_references": [],
        "execution_time_ms": 0.1,
        "command_id": cid,
    }


def make_transport(fake: Optional[FakeUE] = None) -> httpx.MockTransport:
    fake = fake or FakeUE()
    return httpx.MockTransport(fake.handler)
