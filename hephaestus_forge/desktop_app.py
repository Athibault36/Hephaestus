# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Hephaestus Desktop — native shell for Mission Control + multi-project registry.

v1: pywebview window when installed; falls back to default browser.
"""

from __future__ import annotations

import importlib.util
import json
import mimetypes
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable, Optional

from avatar_hub import AvatarHub
from mission_control_server import ObserveServer, prepare_project_dashboard
from project_registry import ProjectRegistry
from thought_hub import ThoughtHub
from agent_job_hub import AgentJobHub

FORGE_ROOT = Path(__file__).resolve().parent
LAUNCHER_DIR = FORGE_ROOT / "templates" / "desktop"
DEFAULT_PORT = 3000


def _load_write_fallback() -> Callable[[Path, str], None]:
    spec = importlib.util.spec_from_file_location("hephaestus_forge_cli", FORGE_ROOT / "forge.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load forge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "_write_mission_control_fallback", None)
    if fn is None:
        raise RuntimeError("forge.py missing _write_mission_control_fallback")
    return fn


class DesktopApp:
    """Project picker + Mission Control in one local server."""

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        remote_api: str = "http://127.0.0.1:8765",
    ):
        self.port = port
        self.remote_api = remote_api
        self.registry = ProjectRegistry.load()
        self.active_project: Optional[Path] = self.registry.active()
        self._mission_server: Optional[ObserveServer] = None
        self._write_fallback = _load_write_fallback()
        self.avatar_hub = AvatarHub()
        self.thought_hub = ThoughtHub()
        self.job_hub = AgentJobHub()

    def _avatar_broadcast(self, state: Optional[str] = None, form: Optional[int] = None, trigger: Optional[str] = None) -> None:
        self.avatar_hub.broadcast(state=state, form=form, trigger=trigger)

    def _serve_launcher_file(self, handler: BaseHTTPRequestHandler) -> bool:
        path = handler.path.split("?")[0]
        if self.active_project is not None:
            return False
        if path in ("/", "/launcher", "/launcher.html"):
            file_path = LAUNCHER_DIR / "launcher.html"
            if not file_path.exists():
                handler.send_error(404, "launcher.html missing")
                return True
            data = file_path.read_bytes()
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        if path.startswith("/launcher/"):
            rel = path[len("/launcher/") :]
            file_path = (LAUNCHER_DIR / rel).resolve()
            if not str(file_path).startswith(str(LAUNCHER_DIR.resolve())):
                handler.send_error(403)
                return True
            if not file_path.is_file():
                handler.send_error(404)
                return True
            data = file_path.read_bytes()
            ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            handler.send_response(200)
            handler.send_header("Content-Type", ctype)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        return False

    def _api_get(self, handler: BaseHTTPRequestHandler) -> bool:
        path = handler.path.split("?")[0]
        if path == "/api/projects":
            payload = {
                "active": self.registry.active_path,
                "projects": [
                    {
                        "path": p.path,
                        "name": p.name,
                        "last_opened": p.last_opened,
                        "valid": p.is_valid(),
                    }
                    for p in self.registry.list_valid()
                ],
            }
            data = json.dumps(payload).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        if path == "/api/health":
            try:
                from preflight_health import run_preflight

                report = run_preflight(self.remote_api, self.active_project)
                payload = report.to_dict()
                payload["ok"] = True
                payload["active_project"] = str(self.active_project) if self.active_project else None
            except Exception as exc:
                payload = {
                    "ok": False,
                    "error": str(exc),
                    "active_project": str(self.active_project) if self.active_project else None,
                    "ue_api": self.remote_api,
                }
            data = json.dumps(payload).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        if path == "/api/avatar/state":
            return self.avatar_hub.handle_get(handler)
        if path == "/api/avatar/stream":
            return self.avatar_hub.handle_get(handler)
        return False

    def _api_post(self, handler: BaseHTTPRequestHandler) -> bool:
        path = handler.path.split("?")[0]
        length = int(handler.headers.get("Content-Length", "0") or 0)
        raw = handler.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            handler.send_error(400, "invalid json")
            return True

        if path == "/api/projects":
            project_path = body.get("path", "").strip()
            if not project_path:
                handler.send_error(400, "path required")
                return True
            try:
                entry = self.registry.add(Path(project_path), name=body.get("name"))
                self._connect_project(entry.resolved())
                payload = {"ok": True, "path": entry.path, "name": entry.name}
            except ValueError as exc:
                payload = {"ok": False, "error": str(exc)}
            data = json.dumps(payload).encode("utf-8")
            handler.send_response(200 if payload.get("ok") else 400)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        if path == "/api/active":
            project_path = body.get("path", "").strip()
            if not project_path:
                handler.send_error(400, "path required")
                return True
            try:
                root = Path(project_path).expanduser().resolve()
                self.registry.add(root)
                self._connect_project(root)
                payload = {"ok": True, "path": str(root)}
            except ValueError as exc:
                payload = {"ok": False, "error": str(exc)}
            data = json.dumps(payload).encode("utf-8")
            handler.send_response(200 if payload.get("ok") else 400)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True

        return False

    def _connect_project(self, project_root: Path) -> None:
        if self._mission_server:
            self._mission_server.stop()
        dist_dir = prepare_project_dashboard(project_root, self._write_fallback)
        self.active_project = project_root
        self.registry.set_active(project_root)
        self._mission_server = ObserveServer(
            dist_dir=dist_dir,
            port=self.port,
            remote_api=self.remote_api,
            extra_get=self._route_get,
            extra_post=self._route_post,
            on_avatar=self.avatar_hub.callback,
            avatar_hub=self.avatar_hub,
            thought_hub=self.thought_hub,
            job_hub=self.job_hub,
            project_root=project_root,
        )
        self._mission_server.start(blocking=False)

    def _route_get(self, handler: BaseHTTPRequestHandler) -> bool:
        if self._serve_launcher_file(handler):
            return True
        return self._api_get(handler)

    def _route_post(self, handler: BaseHTTPRequestHandler) -> bool:
        return self._api_post(handler)

    def run(
        self,
        project: Optional[Path] = None,
        use_webview: bool = True,
    ) -> None:
        if project:
            self.registry.add(project.expanduser().resolve())
            self._connect_project(project.expanduser().resolve())
        elif self.active_project:
            self._connect_project(self.active_project)
        else:
            # Launcher-only mode: serve picker until user selects a project
            dist_dir = LAUNCHER_DIR
            dist_dir.mkdir(parents=True, exist_ok=True)
            self._mission_server = ObserveServer(
                dist_dir=dist_dir,
                port=self.port,
                remote_api=self.remote_api,
                extra_get=self._route_get,
                extra_post=self._route_post,
                on_avatar=self.avatar_hub.callback,
                avatar_hub=self.avatar_hub,
                thought_hub=self.thought_hub,
                job_hub=self.job_hub,
            )
            self._mission_server.start(blocking=False)

        url = f"http://127.0.0.1:{self.port}/"
        opened = False
        if use_webview:
            try:
                import webview  # type: ignore

                webview.create_window("Hephaestus", url, width=1280, height=840)
                webview.start()
                opened = True
            except ImportError:
                pass
        if not opened:
            webbrowser.open(url)
            try:
                import time
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
        if self._mission_server:
            self._mission_server.stop()


def run_desktop(
    project: Optional[Path] = None,
    port: int = DEFAULT_PORT,
    api: str = "http://127.0.0.1:8765",
    browser_only: bool = False,
) -> None:
    app = DesktopApp(port=port, remote_api=api)
    app.run(project=project, use_webview=not browser_only)


if __name__ == "__main__":
    run_desktop()
