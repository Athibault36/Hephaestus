# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Live agent thought broadcast for Mission Control SSE."""

from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler
from typing import Any, Optional


class ThoughtHub:
    """Thread-safe thought stream for observe-act and chat runs."""

    def __init__(self) -> None:
        self._listeners: list[queue.Queue[bytes]] = []
        self._lock = threading.Lock()
        self._busy = False
        self._last: dict[str, Any] = {}
        self._recent: list[dict[str, Any]] = []

    @property
    def busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        with self._lock:
            self._busy = busy
        self.publish("status", "agent busy" if busy else "agent idle", {"busy": busy})

    def publish(self, kind: str, content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        payload = {
            "kind": kind,
            "content": content,
            "metadata": metadata or {},
            "busy": self._busy,
            "ts": time.time(),
        }
        with self._lock:
            self._last = payload
            self._recent.append(payload)
            if len(self._recent) > 200:
                self._recent = self._recent[-200:]
            data = json.dumps(payload).encode("utf-8")
            dead: list[queue.Queue[bytes]] = []
            for q in self._listeners:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._listeners.remove(q)

    def callback(self, kind: str, content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        self.publish(kind, content, metadata)

    def recent(self, limit: int = 120) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent[-limit:])

    def handle_get(self, handler: BaseHTTPRequestHandler) -> bool:
        path = handler.path.split("?")[0]
        if path == "/agent/thoughts/last":
            with self._lock:
                data = json.dumps(self._last).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        if path == "/agent/thoughts/stream":
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Connection", "keep-alive")
            handler.end_headers()
            q: queue.Queue[bytes] = queue.Queue(maxsize=64)
            with self._lock:
                self._listeners.append(q)
                if self._last:
                    initial = json.dumps(self._last).encode("utf-8")
                else:
                    initial = json.dumps({
                        "kind": "status",
                        "content": "connected",
                        "metadata": {},
                        "busy": self._busy,
                        "ts": time.time(),
                    }).encode("utf-8")
                handler.wfile.write(b"data: " + initial + b"\n\n")
                handler.wfile.flush()
            try:
                while True:
                    try:
                        data = q.get(timeout=15)
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
