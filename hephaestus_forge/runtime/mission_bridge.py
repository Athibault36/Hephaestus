"""Stream agent activity to the Mission Control dashboard over Socket.IO.

Mission Control (``store/missionControlStore.ts``) connects a Socket.IO client
and listens for ``thought``, ``agentState``, ``actors``, ``assets`` and
``metrics`` events. This bridge maps :class:`AgentRuntime` trajectory events onto
those channels so the dashboard's Chain-of-Thought / status panels populate live.

The event-mapping layer is decoupled from the network server (inject a fake
emitter) so it can be unit tested without sockets.
"""

from __future__ import annotations

import base64
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol

from .orchestrator import TrajectoryEvent

# TrajectoryEvent.type -> ThoughtEntry['type'] accepted by the dashboard store.
_THOUGHT_TYPE_MAP = {
    "observation": "observation",
    "thought": "plan",
    "action": "action",
    "tool_result": "tool_result",
    "error": "error",
    "final": "reflection",
}

# TrajectoryEvent.type -> AgentState accepted by the dashboard store.
_AGENT_STATE_MAP = {
    "observation": "listening",
    "thought": "thinking",
    "action": "acting",
    "tool_result": "acting",
    "error": "error",
    "final": "idle",
}


class Emitter(Protocol):
    def emit(self, event: str, data: Any) -> None: ...


def _now_ms() -> int:
    return int(time.time() * 1000)


class MissionBridge:
    """Maps agent events to dashboard Socket.IO events.

    Args:
        port: Socket.IO port the dashboard connects to (default 8081).
        server: Optional emitter (e.g. a ``socketio.Server`` or a test double).
            When omitted, :meth:`start` creates a threaded Socket.IO server.
    """

    def __init__(self, port: int = 8081, server: Optional[Emitter] = None):
        self.port = port
        self._server = server
        self._wsgi_thread: Optional[threading.Thread] = None
        self._httpd = None
        self._actors: List[Dict[str, Any]] = []
        self._tool_calls = 0
        self._latency_total_ms = 0.0
        self._last_tool_ms = 0.0

    # -- event mapping (pure; testable) --------------------------------------
    def _emit(self, event: str, data: Any) -> None:
        if self._server is not None:
            self._server.emit(event, data)

    def on_agent_event(self, event: TrajectoryEvent) -> None:
        """Forward a single trajectory event to the dashboard."""
        thought = {
            "id": uuid.uuid4().hex[:8],
            "timestamp": _now_ms(),
            "type": _THOUGHT_TYPE_MAP.get(event.type, "reflection"),
            "content": event.content,
            "metadata": event.metadata or {},
        }
        self._emit("thought", thought)

        state = _AGENT_STATE_MAP.get(event.type)
        if state:
            self._emit("agentState", state)

        # Accumulate spawned actors and push the full list for the World Outliner.
        actors = (event.metadata or {}).get("actors")
        if actors:
            for path in actors:
                self._actors.append(self._actor_info(path))
            self._emit("actors", self._actors)

        # Emit real tool-latency metrics for the Performance panel.
        if event.type in ("tool_result", "error"):
            self._tool_calls += 1
            tool_ms = float((event.metadata or {}).get("execution_time_ms", 0.0) or 0.0)
            self._last_tool_ms = tool_ms
            self._latency_total_ms += tool_ms
            self._emit("metrics", self._metrics_payload())

    def _metrics_payload(self) -> Dict[str, Any]:
        """Full PerformanceMetrics shape; measured latency is real, rest 0 (unmeasured)."""
        return {
            "fps": 0,
            "frameTime": 0.0,
            "gpuTime": 0.0,
            "cpuTime": 0.0,
            "drawCalls": self._tool_calls,  # repurposed: agent tool-call count
            "triangles": 0,
            "textureMemory": 0,
            "latency": {
                "stt": 0,
                "llm": 0,
                "tool": round(self._last_tool_ms, 2),
                "tts": 0,
                "total": round(self._latency_total_ms, 2),
            },
        }

    @staticmethod
    def _actor_info(path: str) -> Dict[str, Any]:
        name = path.rsplit(".", 1)[-1] if path else "Actor"
        return {
            "path": path,
            "name": name,
            "class": "Actor",
            "location": [0, 0, 0],
            "rotation": [0, 0, 0],
            "scale": [1, 1, 1],
            "isSelected": False,
            "components": [],
        }

    def emit_frame(self, png_bytes: bytes, width: int = 0, height: int = 0) -> None:
        """Relay a captured viewport frame to the dashboard as a PNG data URL."""
        if not png_bytes:
            return
        data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        self._emit("frame", {"dataUrl": data_url, "width": width, "height": height, "timestamp": _now_ms()})

    def emit_voice_active(self, active: bool) -> None:
        """Tell the dashboard whether Hephaestus is actively listening."""
        self._emit("voiceActive", bool(active))

    def emit_speaker(self, recognized: Optional[bool]) -> None:
        """Report the current speaker: True=operator, False=other, None=idle."""
        self._emit("speaker", {"recognized": bool(recognized)} if recognized is not None else None)

    def reset(self) -> None:
        self._actors = []
        self._tool_calls = 0
        self._latency_total_ms = 0.0
        self._last_tool_ms = 0.0

    # -- optional live server ------------------------------------------------
    def start(self) -> "MissionBridge":
        """Start a threaded Socket.IO server the dashboard can connect to."""
        import socketio
        from socketserver import ThreadingMixIn
        from wsgiref.simple_server import WSGIServer, make_server

        sio = socketio.Server(async_mode="threading", cors_allowed_origins="*")
        app = socketio.WSGIApp(sio)
        self._server = sio

        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        self._httpd = make_server("127.0.0.1", self.port, app, server_class=ThreadingWSGIServer)
        self._wsgi_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._wsgi_thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
