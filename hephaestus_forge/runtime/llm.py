"""Minimal OpenAI-compatible chat client with tool-calling.

Works against any OpenAI-compatible endpoint: the local ``llama.cpp`` server
started by :mod:`hephaestus_forge.gpu_dev.llama_manager`, or a hosted NIM. Kept
tiny and synchronous so the orchestrator stays easy to test with a fake LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class LLM(Protocol):
    """Structural type the orchestrator depends on (real client or a fake)."""

    def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> LLMResponse: ...


def _parse_arguments(raw_args: Any) -> Dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if not raw_args:
        return {}
    try:
        parsed = json.loads(raw_args)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iter_json_values(text: str):
    """Yield JSON objects/arrays embedded anywhere in ``text``.

    Scans for balanced ``{...}`` and ``[...]`` spans (respecting strings) and
    attempts to decode each. Tolerates surrounding prose and code fences.
    """
    if not text:
        return
    openers = {"{": "}", "[": "]"}
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in openers:
            close = openers[ch]
            depth = 0
            in_str = False
            escape = False
            j = i
            while j < n:
                c = text[j]
                if in_str:
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == '"':
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == ch:
                    depth += 1
                elif c == close:
                    depth -= 1
                    if depth == 0:
                        candidate = text[i : j + 1]
                        try:
                            yield json.loads(candidate)
                        except json.JSONDecodeError:
                            pass
                        i = j
                        break
                j += 1
        i += 1


def _to_tool_call(obj: Dict[str, Any], index: int) -> Optional["ToolCall"]:
    """Normalize a dict into a ToolCall across common conventions, or None."""
    name = obj.get("tool") or obj.get("name") or obj.get("action") or obj.get("function")
    if not name or not isinstance(name, str):
        return None
    raw_args = (
        obj.get("args")
        or obj.get("arguments")
        or obj.get("action_input")
        or obj.get("parameters")
        or obj.get("input")
        or {}
    )
    return ToolCall(id=obj.get("id", f"text_{index}"), name=name, arguments=_parse_arguments(raw_args))


def extract_tool_calls_from_text(content: str) -> List[ToolCall]:
    """Best-effort recovery of tool calls from a model's plain text.

    Supports models that emit JSON tool directives in ``content`` instead of the
    OpenAI ``tool_calls`` field, e.g. ``{"tool": "world.spawn_actor",
    "args": {...}}``, ReAct ``{"action": ..., "action_input": {...}}``, or a JSON
    array of such objects.
    """
    calls: List[ToolCall] = []
    for value in _iter_json_values(content):
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                call = _to_tool_call(item, len(calls))
                if call is not None:
                    calls.append(call)
        if calls:
            break  # first JSON payload that yields tool calls wins
    return calls


class LLMClient:
    """A thin OpenAI-compatible ``/chat/completions`` client."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "nem",
        model: str = "nvidia/nemotron-3-ultra",
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: float = 120.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=timeout, transport=transport
        )

    def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        tool_calls: List[ToolCall] = []
        for tc in message.get("tool_calls", []) or []:
            fn = tc.get("function", {}) or {}
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=_parse_arguments(fn.get("arguments")),
                )
            )
        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", ""),
            raw=data,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
