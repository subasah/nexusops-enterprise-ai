"""
NexusOps OpenAI / OpenAI-Compatible Model Provider.

Supports live API calls to OpenAI (GPT-4o, o3-mini), Anthropic, Gemini, or local vLLM/Ollama endpoints.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx

from nexusops.routing.providers.base import BaseLLMProvider, LLMResponse, ToolCallRequest


class OpenAICompatibleProvider(BaseLLMProvider):
    """Production provider for OpenAI-compatible REST APIs."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        cost_per_1k_input: float = 0.005,
        cost_per_1k_output: float = 0.015,
    ):
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        start_time = time.time()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()

        latency_ms = round((time.time() - start_time) * 1000, 2)
        choice = data["choices"][0]["message"]
        content = choice.get("content")
        raw_tool_calls = choice.get("tool_calls") or []

        tool_calls: List[ToolCallRequest] = []
        for tc in raw_tool_calls:
            import json
            args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
            tool_calls.append(ToolCallRequest(
                call_id=tc["id"],
                name=tc["function"]["name"],
                arguments=args
            ))

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost_usd = (
            (prompt_tokens / 1000.0) * self.cost_per_1k_input +
            (completion_tokens / 1000.0) * self.cost_per_1k_output
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=self.model_name,
            latency_ms=latency_ms,
            estimated_cost_usd=cost_usd
        )
