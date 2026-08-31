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
