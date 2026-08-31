"""Structured error taxonomy for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class ErrorKind(str, Enum):
    TRANSPORT = "transport"
    VALIDATION = "validation"
    COMMAND = "command"
    TOOL = "tool"
    LLM = "llm"
    AUTH = "auth"


@dataclass(frozen=True)
class ErrorInfo:
    kind: ErrorKind
    code: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"error_kind": self.kind.value, "error_code": self.code, "error": self.message}


def transport_error(code: str, message: str) -> ErrorInfo:
    return ErrorInfo(ErrorKind.TRANSPORT, code, message)


def validation_error(code: str, message: str) -> ErrorInfo:
    return ErrorInfo(ErrorKind.VALIDATION, code, message)


def command_error(code: str, message: str) -> ErrorInfo:
    return ErrorInfo(ErrorKind.COMMAND, code, message)


def tool_error(code: str, message: str) -> ErrorInfo:
    return ErrorInfo(ErrorKind.TOOL, code, message)


def auth_error(code: str, message: str) -> ErrorInfo:
    return ErrorInfo(ErrorKind.AUTH, code, message)


def llm_error(code: str, message: str) -> ErrorInfo:
    return ErrorInfo(ErrorKind.LLM, code, message)


def infer_command_error(message: str) -> ErrorInfo:
    lower = (message or "").lower()
    if "unauthorized" in lower or "auth" in lower:
        return auth_error("BRIDGE_UNAUTHORIZED", message)
    if "unreachable" in lower or "timeout" in lower or "connection" in lower:
        return transport_error("BRIDGE_UNREACHABLE", message)
    return command_error("COMMAND_FAILED", message or "command failed")


class ToolError(Exception):
    """Raised for unknown tools or invalid tool arguments (not engine failures)."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "TOOL_INVALID_ARGS",
        kind: ErrorKind = ErrorKind.VALIDATION,
    ):
        super().__init__(message)
        self.info = validation_error(code, message) if kind == ErrorKind.VALIDATION else tool_error(code, message)
