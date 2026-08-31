"""Deploy-time helpers: service readiness probes and process lifecycle."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Callable, Dict, List, Optional, Tuple

from .health import default_http_getter

HttpGetter = Callable[[str, float], Tuple[bool, str]]


def wait_for_url(
    url: str,
    *,
    timeout: float = 60.0,
    interval: float = 1.0,
    getter: HttpGetter = default_http_getter,
) -> bool:
    """Poll *url* until it responds or *timeout* seconds elapse."""
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        ok, _detail = getter(url, min(2.0, interval))
        if ok:
            return True
        time.sleep(max(0.1, interval))
    return False


def bridge_env_from_config(config: dict) -> Dict[str, str]:
    """Build subprocess env vars for the UE bridge from a config dict."""
    env: Dict[str, str] = {}
    network = config.get("network") or {}
    security = config.get("security") or {}

    ue_port = network.get("ue_bridge_port")
    if ue_port:
        env["HEPHAESTUS_UE_PORT"] = str(int(ue_port))

    token = (
        os.environ.get("HEPHAESTUS_BRIDGE_TOKEN")
        or security.get("bridge_token")
        or (security.get("api_keys") or {}).get("bridge")
    )
    if token:
        env["HEPHAESTUS_BRIDGE_TOKEN"] = str(token)

    require_auth = security.get("require_auth")
    if require_auth or token:
        env["HEPHAESTUS_REQUIRE_AUTH"] = "1" if (require_auth or token) else "0"

    if security.get("localhost_only", True):
        env["HEPHAESTUS_LOCALHOST_ONLY"] = "1"

    return env


def shutdown_processes(
    processes: List[Tuple[str, subprocess.Popen]],
    *,
    timeout: float = 5.0,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """Terminate child processes gracefully, then kill stragglers."""
    for name, proc in processes:
        if proc.poll() is not None:
            continue
        if log:
            log(f"Stopping {name}...")
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
