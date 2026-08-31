"""HTTP client for the HephaestusBridge command handler.

The UE5.8 plugin exposes ``UHephaestusCommandHandler`` over a small HTTP server
(see ``HephaestusHttpServer``). Every command is a JSON envelope::

    {"command": "world.spawn_actor", "params": {"action": "spawn_actor", ...}}

and the handler replies with the serialized ``FHephaestusCommandResult``::

    {"success": true, "error_message": "", "result_json": "{...}",
     "actor_references": [...], "asset_references": [...],
     "execution_time_ms": 1.2, "command_id": "cmd_1"}

This module is intentionally free of any UE dependency so it can be unit tested
on any platform.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import AUTH_HEADER, RuntimeConfig, load_runtime_config
from .errors import ErrorInfo, auth_error, transport_error

DEFAULT_BASE_URL = "http://127.0.0.1:8099"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 2


class UEError(Exception):
    """Base class for UE bridge errors."""


class UEConnectionError(UEError):
    """Raised when the UE bridge cannot be reached or returns a transport error."""

    def __init__(self, message: str, *, code: str = "BRIDGE_TRANSPORT", info: Optional[ErrorInfo] = None):
        super().__init__(message)
        self.info = info or transport_error(code, message)


@dataclass
class CommandResult:
    """Parsed result of a single command executed by the UE command handler."""

    success: bool
    error_message: str = ""
    result_json: str = "{}"
    asset_references: List[str] = field(default_factory=list)
    actor_references: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    command_id: str = ""
    error_kind: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def result(self) -> Dict[str, Any]:
        """The ``result_json`` payload decoded into a dict (``{}`` if unparseable)."""
        if not self.result_json:
            return {}
        try:
            decoded = json.loads(self.result_json)
        except (json.JSONDecodeError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {"value": decoded}

    @classmethod
    def from_response(cls, data: Dict[str, Any]) -> "CommandResult":
        """Build a result from a decoded HTTP JSON body, tolerating field aliases."""
        return cls(
            success=bool(data.get("success", data.get("bSuccess", False))),
            error_message=str(data.get("error_message", data.get("ErrorMessage", "")) or ""),
            result_json=str(data.get("result_json", data.get("ResultJSON", "{}")) or "{}"),
            asset_references=list(data.get("asset_references", data.get("AssetReferences", [])) or []),
            actor_references=list(data.get("actor_references", data.get("ActorReferences", [])) or []),
            execution_time_ms=float(data.get("execution_time_ms", data.get("ExecutionTimeMs", 0.0)) or 0.0),
            command_id=str(data.get("command_id", data.get("CommandID", "")) or ""),
            error_kind=data.get("error_kind"),
            error_code=data.get("error_code"),
        )

    @classmethod
    def error(cls, message: str) -> "CommandResult":
        return cls(success=False, error_message=message)


class UEClient:
    """Synchronous HTTP client for the HephaestusBridge command handler.

    Args:
        base_url: Root URL of the plugin HTTP server.
        timeout: Per-request timeout in seconds.
        max_retries: Extra attempts for transient transport errors (not 4xx/5xx
            or command-level failures, which are surfaced without retrying).
        transport: Optional httpx transport (used by tests to mock the server).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: Optional[httpx.BaseTransport] = None,
        auth_token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.auth_token = auth_token
        headers = {AUTH_HEADER: auth_token} if auth_token else None
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport, headers=headers
        )

    @classmethod
    def from_env(cls, **kwargs: Any) -> "UEClient":
        """Create a client honoring ``HEPHAESTUS_UE_URL`` and bridge token env vars."""
        cfg = load_runtime_config()
        return cls(
            base_url=os.environ.get("HEPHAESTUS_UE_URL", cfg.ue_bridge_url),
            auth_token=kwargs.pop("auth_token", cfg.ue_bridge_token),
            **kwargs,
        )

    @classmethod
    def from_config(cls, config: Optional[RuntimeConfig] = None, **kwargs: Any) -> "UEClient":
        """Create a client from a :class:`RuntimeConfig` (or loaded project config)."""
        cfg = config or load_runtime_config()
        return cls(
            base_url=kwargs.pop("base_url", cfg.ue_bridge_url),
            auth_token=kwargs.pop("auth_token", cfg.ue_bridge_token),
            **kwargs,
        )

    # -- transport helpers ---------------------------------------------------
    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(path, json=payload)
            except httpx.TransportError as exc:  # connect/read/timeout
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(min(0.5 * (2 ** attempt), 2.0))
                    continue
                raise UEConnectionError(f"Failed to reach UE bridge at {self.base_url}: {exc}") from exc
            if resp.status_code >= 500:
                # Server-side failure: worth one or more retries.
                last_exc = UEConnectionError(f"UE bridge returned HTTP {resp.status_code}")
                if attempt < self.max_retries:
                    time.sleep(min(0.5 * (2 ** attempt), 2.0))
                    continue
                raise last_exc
            if resp.status_code == 401:
                raise UEConnectionError(
                    "UE bridge rejected request (401): unauthorized",
                    code="BRIDGE_UNAUTHORIZED",
                    info=auth_error("BRIDGE_UNAUTHORIZED", "unauthorized"),
                )
            if resp.status_code >= 400:
                raise UEConnectionError(f"UE bridge rejected request ({resp.status_code}): {resp.text[:200]}")
            try:
                data = resp.json()
                return data if isinstance(data, dict) else {"value": data}
            except json.JSONDecodeError as exc:
                raise UEConnectionError(f"UE bridge returned non-JSON body: {resp.text[:200]}") from exc
        # Unreachable, but keeps type checkers happy.
        raise UEConnectionError(str(last_exc) if last_exc else "unknown error")

    def _get(self, path: str) -> Dict[str, Any]:
        try:
            resp = self._client.get(path)
        except httpx.TransportError as exc:
            raise UEConnectionError(f"Failed to reach UE bridge at {self.base_url}: {exc}") from exc
        if resp.status_code == 401:
            raise UEConnectionError(
                "UE bridge rejected request (401): unauthorized",
                code="BRIDGE_UNAUTHORIZED",
                info=auth_error("BRIDGE_UNAUTHORIZED", "unauthorized"),
            )
        if resp.status_code >= 400:
            raise UEConnectionError(f"UE bridge error ({resp.status_code}): {resp.text[:200]}")
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"value": data}
        except json.JSONDecodeError as exc:
            raise UEConnectionError(f"UE bridge returned non-JSON body: {resp.text[:200]}") from exc

    def _get_bytes(self, path: str) -> bytes:
        try:
            resp = self._client.get(path)
        except httpx.TransportError as exc:
            raise UEConnectionError(f"Failed to reach UE bridge at {self.base_url}: {exc}") from exc
        if resp.status_code == 401:
            raise UEConnectionError(
                "UE bridge rejected request (401): unauthorized",
                code="BRIDGE_UNAUTHORIZED",
                info=auth_error("BRIDGE_UNAUTHORIZED", "unauthorized"),
            )
        if resp.status_code >= 400:
            raise UEConnectionError(f"UE bridge error ({resp.status_code}) for {path}")
        return resp.content

    # -- public API ----------------------------------------------------------
    def is_healthy(self) -> bool:
        """Return True if the bridge answers its health endpoint."""
        try:
            data = self._get("/health")
        except UEError:
            return False
        status = str(data.get("status", "")).lower()
        return status in ("ok", "healthy", "ready") or bool(data.get("healthy"))

    def health(self) -> Dict[str, Any]:
        """Return the raw health payload (raises ``UEConnectionError`` if unreachable)."""
        return self._get("/health")

    def available_commands(self) -> List[str]:
        """List command names the bridge advertises."""
        data = self._get("/commands")
        commands = data.get("commands", data)
        if isinstance(commands, list):
            return [str(c) for c in commands]
        return []

    def execute(self, command: str, params: Optional[Dict[str, Any]] = None) -> CommandResult:
        """Execute a single command and return its parsed result.

        Command-level failures (``success == false``) are returned, not raised;
        only transport/connection problems raise ``UEConnectionError``.
        """
        envelope = {"command": command, "params": params or {}}
        data = self._post("/command", envelope)
        return CommandResult.from_response(data)

    def execute_batch(self, commands: List[Dict[str, Any]]) -> List[CommandResult]:
        """Execute a list of ``{"command", "params"}`` envelopes in order."""
        data = self._post("/batch", {"commands": commands})
        results = data.get("results", [])
        return [CommandResult.from_response(r) for r in results]

    def get_frame(self, frame_id: int) -> bytes:
        """Fetch the raw image bytes (PNG) for a captured frame by id."""
        return self._get_bytes(f"/frame/{int(frame_id)}")

    def capture_frame(self, include_image: bool = False) -> Tuple[CommandResult, Optional[bytes]]:
        """Capture a viewport frame; optionally also fetch its image bytes.

        Returns ``(result, image_bytes_or_None)``. The command result carries
        frame metadata (frame_id, width, height); the bytes are the encoded
        image suitable for feeding a vision model in the observe loop.
        """
        result = self.execute("vision.capture_frame", {"action": "capture_frame"})
        image: Optional[bytes] = None
        if include_image and result.success:
            frame_id = result.result.get("frame_id")
            if frame_id is not None:
                image = self.get_frame(int(frame_id))
        return result, image

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UEClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
