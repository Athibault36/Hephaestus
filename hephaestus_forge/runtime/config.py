"""Runtime URLs, ports, and security settings from config.yaml or environment.

Centralizes values that were previously hard-coded across the CLI, UE client,
Mission Control bridge, and dashboard so a single ``config.yaml`` (plus env
overrides) drives connectivity.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT_HOST = "127.0.0.1"
DEFAULT_UE_BRIDGE_PORT = 8099
DEFAULT_MISSION_BRIDGE_PORT = 8081
DEFAULT_LLM_PORT = 8080
DEFAULT_DASHBOARD_PORT = 3000
AUTH_HEADER = "X-Hephaestus-Token"


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved connectivity and security settings for the agent runtime."""

    ue_bridge_url: str
    ue_bridge_token: Optional[str]
    llm_base_url: str
    mission_bridge_host: str
    mission_bridge_port: int
    dashboard_port: int
    localhost_only: bool
    require_auth: bool

    @property
    def auth_headers(self) -> Dict[str, str]:
        if self.ue_bridge_token:
            return {AUTH_HEADER: self.ue_bridge_token}
        return {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        network = data.get("network") or {}
        inference = (data.get("models") or {}).get("inference") or {}
        mission = data.get("mission_control") or {}
        security = data.get("security") or {}

        host = str(inference.get("host", DEFAULT_HOST))
        llm_port = int(inference.get("port", DEFAULT_LLM_PORT))
        ue_port = int(network.get("ue_bridge_port", DEFAULT_UE_BRIDGE_PORT))
        bridge_port = int(network.get("webrtc_port", DEFAULT_MISSION_BRIDGE_PORT))
        mc_host = str(mission.get("host", DEFAULT_HOST))
        mc_port = int(mission.get("port", network.get("dashboard_port", DEFAULT_DASHBOARD_PORT)))

        token = (
            os.environ.get("HEPHAESTUS_BRIDGE_TOKEN")
            or security.get("bridge_token")
            or (security.get("api_keys") or {}).get("bridge")
        )
        if token == "":
            token = None
        token = str(token) if token else None

        ue_url = os.environ.get("HEPHAESTUS_UE_URL") or f"http://{host}:{ue_port}"
        llm_url = os.environ.get("HEPHAESTUS_LLM_URL") or f"http://{host}:{llm_port}/v1"

        return cls(
            ue_bridge_url=ue_url.rstrip("/"),
            ue_bridge_token=token,
            llm_base_url=llm_url.rstrip("/"),
            mission_bridge_host=str(os.environ.get("HEPHAESTUS_BRIDGE_HOST", mc_host)),
            mission_bridge_port=int(os.environ.get("HEPHAESTUS_BRIDGE_PORT", bridge_port)),
            dashboard_port=mc_port,
            localhost_only=bool(security.get("localhost_only", True)),
            require_auth=bool(security.get("require_auth", False)),
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> "RuntimeConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def defaults(cls) -> "RuntimeConfig":
        return cls.from_dict({})


def find_project_config(start: Optional[Path] = None) -> Optional[Path]:
    """Locate ``.hephaestus_forge/config.yaml`` walking up from *start*."""
    cur = (start or Path.cwd()).resolve()
    for directory in [cur, *cur.parents]:
        candidate = directory / ".hephaestus_forge" / "config.yaml"
        if candidate.is_file():
            return candidate
    template = Path(__file__).resolve().parents[1] / "forge_config" / "config.yaml"
    return template if template.is_file() else None


def load_runtime_config(project_root: Optional[Path] = None) -> RuntimeConfig:
    """Load runtime config from the project or fall back to defaults + env."""
    path = find_project_config(project_root)
    if path is not None:
        return RuntimeConfig.from_yaml(path)
    return RuntimeConfig.defaults()


@dataclass(frozen=True)
class ObservabilityConfig:
    log_format: str = "text"
    log_dir: str = "logs"
    metrics_enabled: bool = False
    metrics_host: str = DEFAULT_HOST
    metrics_port: int = 9090
    tracing_enabled: bool = False
    tracing_endpoint: str = "http://127.0.0.1:4318/v1/traces"


def load_observability_config(project_root: Optional[Path] = None) -> ObservabilityConfig:
    path = find_project_config(project_root)
    data: Dict[str, Any] = {}
    if path is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    obs = data.get("observability") or {}
    metrics = obs.get("metrics") or {}
    tracing = obs.get("tracing") or {}
    return ObservabilityConfig(
        log_format=str(obs.get("log_format", "text")),
        log_dir=str(obs.get("log_dir", "logs")),
        metrics_enabled=bool(metrics.get("enabled", False)),
        metrics_host=str(metrics.get("host", DEFAULT_HOST)),
        metrics_port=int(metrics.get("port", 9090)),
        tracing_enabled=bool(tracing.get("enabled", False)),
        tracing_endpoint=str(tracing.get("endpoint", "http://127.0.0.1:4318/v1/traces")),
    )


def default_trajectory_log_path(project_root: Path, obs: ObservabilityConfig) -> Path:
    return project_root / obs.log_dir / "agent_trajectory.jsonl"
