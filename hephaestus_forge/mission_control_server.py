# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Mission Control HTTP server (observe + desktop app)."""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from avatar_hub import AvatarHub
from thought_hub import ThoughtHub
from agent_job_hub import AgentJobHub


FORGE_ROOT = Path(__file__).resolve().parent


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Handle SSE + API concurrently (single-threaded server deadlocks on EventSource)."""

    daemon_threads = True
    allow_reuse_address = True

try:
    from hephaestus_forge.cloud.nim_client import DEFAULT_PLANNER_MODEL
except ImportError:
    from cloud.nim_client import DEFAULT_PLANNER_MODEL  # type: ignore


def prepare_project_dashboard(project_root: Path, write_fallback) -> Path:
    """Refresh Mission Control dist for a UE project; write_fallback(dist_dir, api)."""
    import yaml

    forge_dir = project_root / ".hephaestus_forge"
    config_path = forge_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    mission_dir = cfg.get("paths", {}).get("mission_control_dir", "MissionControl")
    dist_dir = project_root / mission_dir / "dist"
    write_fallback(dist_dir, "")
    return dist_dir


def make_handler(
    dist_dir: Path,
    remote_api: str,
    extra_get: Optional[Callable[[http.server.BaseHTTPRequestHandler], bool]] = None,
    extra_post: Optional[Callable[[http.server.BaseHTTPRequestHandler], bool]] = None,
    on_avatar: Optional[Callable[[str, Optional[int], Optional[str]], None]] = None,
    avatar_hub: Optional[AvatarHub] = None,
    thought_hub: Optional[ThoughtHub] = None,
    job_hub: Optional[AgentJobHub] = None,
    project_root: Optional[Path] = None,
):
    """Build SPAHandler for Mission Control + UE proxy + agent routes."""

    class SPAHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dist_dir), **kwargs)

        def _proxy(self, method: str) -> bool:
            path = self.path.split("?")[0]
            if not path.startswith("/v1/"):
                return False
            url = remote_api.rstrip("/") + self.path
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length > 0 else None
            req = urllib.request.Request(url, data=body, method=method)
            ctype = self.headers.get("Content-Type")
            if ctype:
                req.add_header("Content-Type", ctype)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", resp.headers.get("Content-Type", "application/octet-stream"))
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
            except urllib.error.HTTPError as exc:
                err_body = exc.read()
                self.send_response(exc.code)
                self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            except Exception as exc:
                msg = json.dumps({"ok": False, "error": str(exc)}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            return True

        def _json_response(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _handle_agent(self) -> bool:
            path = self.path.split("?")[0]
            if path == "/agent/health" and self.command == "GET":
                try:
                    sys.path.insert(0, str(FORGE_ROOT))
                    from preflight_health import run_preflight

                    report = run_preflight(remote_api, project_root)
                    payload = report.to_dict()
                    llm_check = next((c for c in report.checks if c.name == "planner"), None)
                    nim_check = next((c for c in report.checks if c.name == "nim_api_key"), None)
                    vision_check = next((c for c in report.checks if c.name == "vision_planner"), None)
                    cap_check = next((c for c in report.checks if c.name == "bridge_capabilities"), None)
                    payload.update({
                        "ok": True,
                        "planner": report.planner_model,
                        "llm_available": bool(llm_check and llm_check.ok),
                        "llm_error": "" if (llm_check and llm_check.ok) else (llm_check.detail if llm_check else ""),
                        "nim_key_set": bool(nim_check and nim_check.ok),
                        "vision_mode": vision_check.detail if vision_check else "",
                        "bridge_capabilities": cap_check.detail if cap_check else "",
                        "bridge_capabilities_ok": bool(cap_check and cap_check.ok),
                        "ue": remote_api,
                        "project": str(project_root) if project_root else "",
                        "ready_for_goals": report.ready,
                    })
                    self._json_response(200, payload)
                except Exception as exc:
                    self._json_response(200, {
                        "ok": True,
                        "planner": DEFAULT_PLANNER_MODEL,
                        "llm_available": False,
                        "llm_error": str(exc),
                        "ue": remote_api,
                        "project": str(project_root) if project_root else "",
                    })
                return True
            if path == "/agent/session" and self.command == "GET":
                try:
                    sys.path.insert(0, str(FORGE_ROOT))
                    from agent_chat import get_store

                    session = get_store(project_root).active().to_dict()
                    self._json_response(200, {"ok": True, "session": session})
                except Exception as exc:
                    self._json_response(500, {"ok": False, "error": str(exc)})
                return True
            if path == "/agent/export" and self.command == "GET":
                try:
                    sys.path.insert(0, str(FORGE_ROOT))
                    from agent_chat import get_store

                    thoughts = thought_hub.recent() if thought_hub else []
                    bundle = get_store(project_root).active().export_bundle(thoughts=thoughts)
                    self._json_response(200, {"ok": True, **bundle})
                except Exception as exc:
                    self._json_response(500, {"ok": False, "error": str(exc)})
                return True
            if path.startswith("/agent/job/") and self.command == "GET":
                job_id = path.split("/agent/job/", 1)[-1].strip("/")
                if not job_hub:
                    self._json_response(503, {"ok": False, "error": "job_hub unavailable"})
                    return True
                job = job_hub.get(job_id)
                if not job:
                    self._json_response(404, {"ok": False, "error": "job_not_found"})
                    return True
                self._json_response(200, {"ok": True, **job})
                return True
            if path == "/agent/chat" and self.command == "POST":
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._json_response(400, {"ok": False, "error": "invalid_json"})
                    return True
                try:
                    sys.path.insert(0, str(FORGE_ROOT))
                    from agent_orchestrator import run_agent

                    thoughts: list[dict] = []

                    def on_thought(kind: str, content: str, metadata: dict) -> None:
                        thoughts.append({"kind": kind, "content": content, "metadata": metadata})
                        if thought_hub:
                            thought_hub.publish(kind, content, metadata)

                    def on_avatar_cb(state: str, form: Optional[int] = None, trigger: Optional[str] = None) -> None:
                        if on_avatar:
                            on_avatar(state, form, trigger)
                        elif avatar_hub:
                            avatar_hub.broadcast(state=state, form=form, trigger=trigger)

                    def _run_chat() -> dict:
                        if thought_hub:
                            thought_hub.set_busy(True)
                        try:
                            return run_agent(
                                body.get("message", ""),
                                project_root=project_root,
                                remote_api=remote_api,
                                max_steps=int(body.get("max_steps", 20)),
                                mode=str(body.get("mode", "auto")),
                                reset=bool(body.get("reset", False)),
                                on_thought=on_thought,
                                on_avatar=on_avatar_cb,
                            )
                        finally:
                            if thought_hub:
                                thought_hub.set_busy(False)

                    if body.get("sync") or not job_hub:
                        payload = _run_chat()
                        self._json_response(200, payload)
                    else:
                        job_id = job_hub.start("chat", _run_chat)
                        if thought_hub:
                            thought_hub.publish(
                                "status",
                                "Chat job started",
                                {"job_id": job_id, "busy": True},
                            )
                        self._json_response(202, {
                            "ok": True,
                            "accepted": True,
                            "job_id": job_id,
                            "status": "running",
                        })
                except Exception as exc:
                    self._json_response(500, {"ok": False, "error": str(exc)})
                return True
            if path == "/agent/search" and self.command == "GET":
                try:
                    from urllib.parse import parse_qs, urlparse

                    qs = parse_qs(urlparse(self.path).query)
                    query = (qs.get("q") or [""])[0]
                    sys.path.insert(0, str(FORGE_ROOT))
                    from agent_asset import search_project_assets
                    from ue_agent_loop import RemoteUeClient

                    client = RemoteUeClient(remote_api, timeout=30.0)
                    assets: list[str] = []
                    for cls in ("", "SkeletalMesh", "StaticMesh"):
                        for p in search_project_assets(client, query, asset_class=cls, limit=8):
                            if p not in assets:
                                assets.append(p)
                    self._json_response(200, {"ok": True, "query": query, "assets": assets[:20]})
                except Exception as exc:
                    self._json_response(500, {"ok": False, "error": str(exc)})
                return True
            if path == "/agent/spawn" and self.command == "POST":
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._json_response(400, {"ok": False, "error": "invalid_json"})
                    return True
                try:
                    sys.path.insert(0, str(FORGE_ROOT))
                    from agent_asset import spawn_asset_in_view
                    from ue_agent_loop import RemoteUeClient

                    asset_path = str(body.get("asset_path") or body.get("path") or "").strip()
                    if not asset_path:
                        self._json_response(400, {"ok": False, "error": "asset_path required"})
                        return True
                    client = RemoteUeClient(remote_api, timeout=60.0)
                    results = spawn_asset_in_view(
                        client, asset_path, with_light=bool(body.get("with_light", True)),
                    )
                    ok = all(r.get("success") for r in results) if results else False
                    self._json_response(200, {
                        "ok": ok,
                        "asset_path": asset_path,
                        "results": results,
                    })
                except Exception as exc:
                    self._json_response(500, {"ok": False, "error": str(exc)})
                return True
            if path in ("/agent/step", "/agent/loop") and self.command == "POST":
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._json_response(400, {"ok": False, "error": "invalid_json"})
                    return True
                try:
                    sys.path.insert(0, str(FORGE_ROOT))
                    from ue_agent_loop import ObserveActLoop, RemoteUeClient
                    from ue_vision_planner import VisionLLMPlanner

                    steps = 1 if path.endswith("/step") else int(body.get("max_steps", body.get("steps", 20)))
                    goal = body.get("goal") or body.get("message") or (
                        "Seed a lit test scene with a few cubes, then idle."
                    )
                    client = RemoteUeClient(remote_api, timeout=60.0)
                    from agent_asset import augment_goal_with_assets

                    goal, asset_matches, _asset_meta = augment_goal_with_assets(client, goal)
                    llm = VisionLLMPlanner(goal=goal, asset_hints=asset_matches)
                    require_nim = body.get("require_nim", True)
                    if isinstance(require_nim, str):
                        require_nim = require_nim.lower() not in ("0", "false", "no")
                    use_llm = llm.available
                    if require_nim and not use_llm:
                        err = llm.last_error or (
                            "NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY required for autonomous operator"
                        )
                        self._json_response(503, {
                            "ok": False,
                            "planner": "",
                            "llm_available": False,
                            "llm_error": err,
                            "goal": goal,
                            "grade": {"met": False, "summary": err, "missing": ["nim_planner"]},
                            "thoughts": [],
                            "steps": [],
                        })
                        return True
                    thoughts: list[dict] = []

                    def on_thought(kind: str, content: str, metadata: dict) -> None:
                        thoughts.append({"kind": kind, "content": content, "metadata": metadata})
                        if thought_hub:
                            thought_hub.publish(kind, content, metadata)

                    def on_avatar_cb(state: str, form: Optional[int] = None, trigger: Optional[str] = None) -> None:
                        if on_avatar:
                            on_avatar(state, form, trigger)
                        elif avatar_hub:
                            avatar_hub.broadcast(state=state, form=form, trigger=trigger)

                    def _run_loop() -> dict:
                        if thought_hub:
                            thought_hub.set_busy(True)
                        try:
                            loop = ObserveActLoop(
                                client=client,
                                on_thought=on_thought,
                                on_avatar=on_avatar_cb,
                                planner=(llm.decide if use_llm else None),
                                goal=goal,
                                asset_hints=asset_matches,
                                require_nim=bool(require_nim),
                            )
                            if path.endswith("/step"):
                                results = loop.run(steps=1, max_steps=1)
                                grade_met = False
                                grade_summary = ""
                            else:
                                results, grade = loop.run_until_goal(max_steps=steps)
                                grade_met = grade.met
                                grade_summary = grade.summary
                            planner_label = llm.model if use_llm else "heuristic"
                            llm_error = llm.last_error
                            if require_nim and not use_llm:
                                llm_error = llm_error or (
                                    "NVIDIA_API_KEY or HEPHAESTUS_LLM_API_KEY required for autonomous operator"
                                )
                            elif not use_llm and not llm_error:
                                llm_error = (
                                    "DeepSeek planner unavailable: set NVIDIA_API_KEY or "
                                    "HEPHAESTUS_LLM_API_KEY (heuristic fallback was used)"
                                )
                            return {
                                "ok": (grade_met if not path.endswith("/step") else all(r.ok for r in results)),
                                "planner": planner_label,
                                "llm_available": use_llm,
                                "llm_error": llm_error,
                                "goal": goal,
                                "grade": {"met": grade_met, "summary": grade_summary} if not path.endswith("/step") else {},
                                "thoughts": thoughts[-40:],
                                "steps": [
                                    {
                                        "step": r.step,
                                        "kind": r.action.kind,
                                        "reason": r.action.reason,
                                        "ok": r.ok,
                                        "lights": r.reobservation.lights,
                                        "meshes": r.reobservation.meshes,
                                    }
                                    for r in results
                                ],
                            }
                        finally:
                            if thought_hub:
                                thought_hub.set_busy(False)

                    if body.get("sync") or not job_hub or path.endswith("/step"):
                        payload = _run_loop()
                        self._json_response(200, payload)
                    else:
                        job_id = job_hub.start("loop", _run_loop)
                        if thought_hub:
                            thought_hub.publish(
                                "status",
                                "Agent loop started",
                                {"job_id": job_id, "busy": True},
                            )
                        self._json_response(202, {
                            "ok": True,
                            "accepted": True,
                            "job_id": job_id,
                            "status": "running",
                        })
                except Exception as exc:
                    self._json_response(500, {"ok": False, "error": str(exc)})
                return True
            return False

        def do_GET(self):
            if extra_get and extra_get(self):
                return
            if avatar_hub and avatar_hub.handle_get(self):
                return
            if thought_hub and thought_hub.handle_get(self):
                return
            if self._handle_agent():
                return
            if self._proxy("GET"):
                return
            rel = self.path.lstrip("/").split("?")[0]
            if rel and not (dist_dir / rel).exists() and "." not in rel:
                self.path = "/index.html"
            return super().do_GET()

        def do_POST(self):
            if extra_post and extra_post(self):
                return
            if self._handle_agent():
                return
            if self._proxy("POST"):
                return
            self.send_error(404)

        def log_message(self, format, *args):
            pass

    return SPAHandler


class ObserveServer:
    """Background-capable Mission Control server."""

    def __init__(
        self,
        dist_dir: Path,
        port: int = 3000,
        remote_api: str = "http://127.0.0.1:8765",
        extra_get: Optional[Callable] = None,
        extra_post: Optional[Callable] = None,
        on_avatar: Optional[Callable[[str, Optional[int], Optional[str]], None]] = None,
        avatar_hub: Optional[AvatarHub] = None,
        thought_hub: Optional[ThoughtHub] = None,
        job_hub: Optional[AgentJobHub] = None,
        project_root: Optional[Path] = None,
    ):
        self.dist_dir = dist_dir
        self.port = port
        self.remote_api = remote_api
        self.extra_get = extra_get
        self.extra_post = extra_post
        self.on_avatar = on_avatar
        self.avatar_hub = avatar_hub
        self.thought_hub = thought_hub
        self.job_hub = job_hub
        self.project_root = project_root
        self._httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, blocking: bool = False) -> None:
        handler = make_handler(
            self.dist_dir,
            self.remote_api,
            extra_get=self.extra_get,
            extra_post=self.extra_post,
            on_avatar=self.on_avatar,
            avatar_hub=self.avatar_hub,
            thought_hub=self.thought_hub,
            job_hub=self.job_hub,
            project_root=self.project_root,
        )
        socketserver.TCPServer.allow_reuse_address = True
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)

        if blocking:
            self._httpd.serve_forever()
            return

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
