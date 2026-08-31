"""
NVIDIA NIM API Client with Token Tracking and Budget Enforcement
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import httpx
import tiktoken
from rich.console import Console

try:
    from hephaestus_forge.cloud.budget_manager import BudgetExceededError, BudgetManager
except ImportError:
    from cloud.budget_manager import BudgetExceededError, BudgetManager

console = Console()


@dataclass
class NIMModel:
    name: str
    input_cost_per_1m: float
    output_cost_per_1m: float
    max_tokens: int
    context_window: int


class NIMClient:
    """NVIDIA NIM API client with automatic budget tracking."""

    MODELS = {
        "nvidia/nemotron-3-ultra": NIMModel(
            name="nvidia/nemotron-3-ultra",
            input_cost_per_1m=0.15,
            output_cost_per_1m=0.60,
            max_tokens=4096,
            context_window=128000,
        ),
        "nvidia/nemotron-3-8b": NIMModel(
            name="nvidia/nemotron-3-8b",
            input_cost_per_1m=0.03,
            output_cost_per_1m=0.12,
            max_tokens=4096,
            context_window=8192,
        ),
        "nvidia/nv-embed-qa": NIMModel(
            name="nvidia/nv-embed-qa",
            input_cost_per_1m=0.01,
            output_cost_per_1m=0.0,
            max_tokens=512,
            context_window=8192,
        ),
    }

    def __init__(
        self,
        budget_manager: BudgetManager,
        api_key: Optional[str] = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
    ):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.base_url = base_url
        self.budget = budget_manager
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            timeout=120.0,
        )
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def estimate_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        model = self.MODELS.get(model_name)
        if not model:
            return 0.0
        input_cost = (input_tokens / 1_000_000) * model.input_cost_per_1m
        output_cost = (output_tokens / 1_000_000) * model.output_cost_per_1m
        return input_cost + output_cost

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> dict | AsyncGenerator[str, None]:
        """Chat completion with budget enforcement."""
        model_info = self.MODELS.get(model)
        if not model_info:
            raise ValueError(f"Unknown model: {model}")

        # Estimate input tokens
        input_text = " ".join(m.get("content", "") for m in messages)
        input_tokens = self.count_tokens(input_text)
        estimated_output = min(max_tokens, model_info.max_tokens)
        estimated_cost = self.estimate_cost(model, input_tokens, estimated_output)

        # Check budget
        if not self.budget.record_spend(estimated_cost, "nim", f"{model} chat"):
            raise BudgetExceededError("Insufficient budget for NIM request")

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        if stream:
            return self._stream_chat(payload, model, input_tokens)
        else:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            # Record actual usage
            usage = data.get("usage", {})
            actual_cost = self.estimate_cost(
                model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            )
            # Adjust: refund difference if over-estimated
            if actual_cost < estimated_cost:
                self.budget.record_spend(actual_cost - estimated_cost, "nim", "refund")

            return data

    async def _stream_chat(
        self, payload: dict, model: str, input_tokens: int
    ) -> AsyncGenerator[str, None]:
        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            output_tokens = 0
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    yield data_str
                    output_tokens += 1  # Approximate

            # Record actual output tokens
            actual_cost = self.estimate_cost(model, input_tokens, output_tokens)
            self.budget.record_spend(actual_cost, "nim", f"{model} stream")

    async def embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        """Get embeddings with budget tracking."""
        model_info = self.MODELS.get(model)
        if not model_info:
            raise ValueError(f"Unknown embedding model: {model}")

        input_tokens = sum(self.count_tokens(t) for t in texts)
        estimated_cost = self.estimate_cost(model, input_tokens, 0)

        if not self.budget.record_spend(estimated_cost, "nim", f"{model} embed"):
            raise BudgetExceededError("Insufficient budget for embeddings")

        payload = {"model": model, "input": texts}
        response = await self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()

        # Record actual usage
        usage = data.get("usage", {})
        actual_cost = self.estimate_cost(model, usage.get("prompt_tokens", 0), 0)
        if actual_cost < estimated_cost:
            self.budget.record_spend(actual_cost - estimated_cost, "nim", "refund")

        return [d["embedding"] for d in data["data"]]

    async def close(self) -> None:
        await self.client.aclose()