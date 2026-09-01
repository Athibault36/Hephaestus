# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Shared avatar state + SSE broadcast for desktop and Mission Control."""

from __future__ import annotations

import json
import queue
import random
import threading
import time
from http.server import BaseHTTPRequestHandler
from typing import Optional

# Hephaestus picks form by mood / phase (not user buttons).
FORM_BY_STATE: dict[str, int] = {
    "idle": 0,        # geometric
    "connecting": 3,  # swarm
    "active": 1,      # organic
    "thinking": 2,    # abstract
    "working": 0,     # geometric — forging
    "success": 1,     # organic — satisfied bloom
    "error": 3,       # swarm — agitated
}

TRIGGER_FORM: dict[str, int] = {
    "observing": 2,
    "planning": 2,
    "acting": 0,
    "executing_spawn_light": 1,
    "executing_spawn_cube": 0,
    "result_ok": 1,
    "result_error": 3,
    "goal_satisfied": 1,
    "loop_start": 3,
    "loop_end": 1,
}


def pick_form(state: str, trigger: Optional[str] = None, seed: int = 0) -> int:
    """Choose avatar form at Hephaestus' whim from state + trigger."""
    if trigger and trigger in TRIGGER_FORM:
        return TRIGGER_FORM[trigger]
    base = FORM_BY_STATE.get(state, 0)
    if trigger:
        # Light whimsy: nudge form from trigger hash without going random every frame.
        nudge = sum(ord(c) for c in trigger) % 4
        return (base + nudge) % 4
    return (base + seed) % 4


class AvatarHub:
    """Thread-safe avatar state with SSE subscribers."""

    def __init__(self) -> None:
        self._state = "idle"
        self._form = 0
        self._listeners: list[queue.Queue[bytes]] = []
        self._lock = threading.Lock()
        self._tick = 0
        t = threading.Thread(target=self._idle_whimsy_loop, daemon=True)
        t.start()

    def _idle_whimsy_loop(self) -> None:
        """Occasionally morph avatar when Hephaestus is resting."""
        while True:
            time.sleep(20 + random.randint(0, 25))
            if self._state in ("idle", "active"):
                self.broadcast(trigger="whimsy")

    @property
    def state(self) -> str:
        return self._state

    @property
    def form(self) -> int:
        return self._form

    def broadcast(
        self,
        state: Optional[str] = None,
        form: Optional[int] = None,
        trigger: Optional[str] = None,
    ) -> None:
        with self._lock:
            if state is not None:
                self._state = state
            if form is None and state is not None:
                self._tick += 1
                form = pick_form(self._state, trigger, self._tick)
            if form is not None:
                self._form = max(0, min(3, form))
            payload = {
                "state": self._state,
                "form": self._form,
                "trigger": trigger,
                "ts": time.time(),
            }
            data = json.dumps(payload).encode("utf-8")
            dead: list[queue.Queue[bytes]] = []
            for q in self._listeners:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._listeners.remove(q)

    def handle_get(self, handler: BaseHTTPRequestHandler) -> bool:
        path = handler.path.split("?")[0]
        if path == "/api/avatar/state":
            payload = {"state": self._state, "form": self._form}
            data = json.dumps(payload).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        if path == "/api/avatar/stream":
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Connection", "keep-alive")
            handler.end_headers()
            q: queue.Queue[bytes] = queue.Queue(maxsize=32)
            with self._lock:
                self._listeners.append(q)
                initial = json.dumps({
                    "state": self._state,
                    "form": self._form,
                    "trigger": "init",
                    "ts": time.time(),
                }).encode("utf-8")
                handler.wfile.write(b"data: " + initial + b"\n\n")
                handler.wfile.flush()
            try:
                while True:
                    try:
                        data = q.get(timeout=20)
                        handler.wfile.write(b"data: " + data + b"\n\n")
                        handler.wfile.flush()
                    except queue.Empty:
                        handler.wfile.write(b": keepalive\n\n")
                        handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with self._lock:
                    if q in self._listeners:
                        self._listeners.remove(q)
            return True
        return False

    def callback(self, state: str, form: Optional[int] = None, trigger: Optional[str] = None) -> None:
        """Drop-in ObserveActLoop on_avatar handler."""
        self.broadcast(state=state, form=form, trigger=trigger)
