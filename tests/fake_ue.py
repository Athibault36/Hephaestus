"""An in-memory fake of the HephaestusBridge HTTP command handler.

Used by tests to exercise the Python runtime end to end without a real engine.
Mirrors the JSON protocol implemented by ``UHephaestusCommandHandler`` /
``HephaestusHttpServer``.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

import httpx

AVAILABLE_COMMANDS = [
    "world.spawn_actor",
    "world.destroy_actor",
    "world.query_spatial",
    "vision.capture_frame",
]


class FakeUE:
    """Records commands and produces plausible command results."""

    def __init__(self) -> None:
        self.received: List[Dict[str, Any]] = []
        self.spawn_counter = 0
        self.frame_counter = 0
        self.fail_transport_times = 0  # simulate N transient 503s before success

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/health":
            return httpx.Response(200, json={"status": "ok", "commands": len(AVAILABLE_COMMANDS)})
        if request.method == "GET" and path == "/commands":
            return httpx.Response(200, json={"commands": AVAILABLE_COMMANDS})
        if request.method == "POST" and path == "/command":
            if self.fail_transport_times > 0:
                self.fail_transport_times -= 1
                return httpx.Response(503, json={"error": "warming up"})
            body = json.loads(request.content.decode() or "{}")
            return httpx.Response(200, json=self._run(body))
        if request.method == "POST" and path == "/batch":
            body = json.loads(request.content.decode() or "{}")
            results = [self._run(env) for env in body.get("commands", [])]
            return httpx.Response(200, json={"results": results})
        return httpx.Response(404, json={"error": f"no route {request.method} {path}"})

    def _run(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        self.received.append(envelope)
        command = envelope.get("command", "")
        params = envelope.get("params", {})
        cid = f"cmd_{len(self.received)}"

        if command == "world.spawn_actor":
            if not params.get("class_path"):
                return _err(cid, "missing class_path")
            self.spawn_counter += 1
            path = f"/Game/Maps/UEDPIE_0_Main.Main:PersistentLevel.SpawnedActor_{self.spawn_counter}"
            return _ok(cid, {"actor_path": path}, actors=[path])
        if command == "world.destroy_actor":
            return _ok(cid, {}) if params.get("actor_path") else _err(cid, "missing actor_path")
        if command == "world.query_spatial":
            return _ok(cid, {"actors": []})
        if command == "vision.capture_frame":
            self.frame_counter += 1
            return _ok(cid, {"frame_id": self.frame_counter, "width": 1920, "height": 1080})
        return _err(cid, f"unknown command {command}")


def _ok(cid: str, result: Dict[str, Any], actors: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "success": True,
        "error_message": "",
        "result_json": json.dumps(result),
        "actor_references": actors or [],
        "asset_references": [],
        "execution_time_ms": 0.5,
        "command_id": cid,
    }


def _err(cid: str, message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "error_message": message,
        "result_json": "{}",
        "actor_references": [],
        "asset_references": [],
        "execution_time_ms": 0.1,
        "command_id": cid,
    }


def make_transport(fake: Optional[FakeUE] = None) -> httpx.MockTransport:
    fake = fake or FakeUE()
    return httpx.MockTransport(fake.handler)
