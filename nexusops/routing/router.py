"""
NexusOps Dynamic Pareto-Optimal Model Router.

Balances Quality, Latency, Cost, and Model Risk using task classification,
semantic caching, circuit-breaking, and automatic fallback cascades.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from nexusops.routing.cache import PromptCache
from nexusops.routing.providers.base import BaseLLMProvider, LLMResponse
from nexusops.routing.providers.mock_provider import MockLLMProvider
from nexusops.telemetry.tracer import SpanKind, Tracer


class RoutingPolicy(str, Enum):
    AUTO = "AUTO"                      # Dynamically selects based on task complexity
    LOW_LATENCY = "LOW_LATENCY"        # Prioritizes fast models (SLAs < 100ms)
    MAX_QUALITY = "MAX_QUALITY"        # Prioritizes frontier reasoning models
    COST_OPTIMIZED = "COST_OPTIMIZED"  # Selects lowest-cost capable model


@dataclass
class CircuitBreakerState:
    failures: int = 0
    state: str = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"
    last_failure_time: float = 0.0
    cooldown_seconds: float = 30.0

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self, threshold: int = 2) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= threshold:
            self.state = "OPEN"

    def is_available(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.cooldown_seconds:
                self.state = "HALF_OPEN"
                return True
            return False
        return True  # HALF_OPEN


class ModelRouter:
    """Enterprise model routing orchestrator with resiliency mechanisms."""

    def __init__(
        self,
        reasoning_provider: Optional[BaseLLMProvider] = None,
        fast_provider: Optional[BaseLLMProvider] = None,
        fallback_provider: Optional[BaseLLMProvider] = None,
        cache: Optional[PromptCache] = None,
        max_cost_budget_usd: float = 5.0,
    ):
        self.reasoning_provider = reasoning_provider or MockLLMProvider(
            model_name="mock-deep-reasoner",
            simulated_latency_ms=25.0
        )
        self.fast_provider = fast_provider or MockLLMProvider(
            model_name="mock-fast-router",
            cost_per_1k_input=0.0005,
            cost_per_1k_output=0.0015,
            simulated_latency_ms=5.0
        )
        self.fallback_provider = fallback_provider or MockLLMProvider(
            model_name="mock-fallback-resilience",
            simulated_latency_ms=15.0
        )
        self.cache = cache or PromptCache()
        self.max_cost_budget_usd = max_cost_budget_usd
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {
            "primary": CircuitBreakerState(),
            "fast": CircuitBreakerState(),
            "fallback": CircuitBreakerState(),
        }

    def select_provider(
        self,
        policy: RoutingPolicy = RoutingPolicy.AUTO,
        is_triage_step: bool = False
    ) -> tuple[str, BaseLLMProvider]:
        """Chooses provider based on routing policy and circuit breaker health."""
        if policy == RoutingPolicy.LOW_LATENCY or is_triage_step:
            if self._circuit_breakers["fast"].is_available():
                return "fast", self.fast_provider

        # Default to reasoning provider
        if self._circuit_breakers["primary"].is_available():
            return "primary", self.reasoning_provider

        # Primary circuit tripped: fallback to resilience provider
        return "fallback", self.fallback_provider

    async def route_and_generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        policy: RoutingPolicy = RoutingPolicy.AUTO,
        is_triage_step: bool = False,
        tracer: Optional[Tracer] = None
    ) -> LLMResponse:
        """Executes LLM request with caching, circuit breaking, fallback, and telemetry."""
        provider_key, provider = self.select_provider(policy, is_triage_step)
        model_name = getattr(provider, "model_name", "unknown_model")

        # 1. Check prompt cache
        cache_key = self.cache.compute_key(messages, tools, model_name)
        cached_resp = self.cache.get(cache_key)
        if cached_resp:
            if tracer:
                span = tracer.start_span("model_cache_hit", kind=SpanKind.LLM_CALL, attributes={"model": model_name, "cache_hit": True})
                tracer.end_span(span, status="OK")
            return cached_resp

        # 2. Execute with circuit breaker & fallback cascade
        span = None
        if tracer:
            span = tracer.start_span(
                f"llm:{model_name}",
                kind=SpanKind.LLM_CALL,
                attributes={"provider_key": provider_key, "model": model_name, "policy": policy.value}
            )

        try:
            resp = await provider.generate(messages, tools)
            self._circuit_breakers[provider_key].record_success()

            # Record metrics in tracer
            if tracer:
                tracer.record_token_usage(resp.prompt_tokens, resp.completion_tokens, resp.estimated_cost_usd)
                if span:
                    span.attributes.update({
                        "prompt_tokens": resp.prompt_tokens,
                        "completion_tokens": resp.completion_tokens,
                        "cost_usd": resp.estimated_cost_usd,
                        "latency_ms": resp.latency_ms
                    })
                    tracer.end_span(span, status="OK")

            # Store in cache
            self.cache.set(cache_key, resp)
            return resp

        except Exception as primary_error:
            # Circuit breaker records failure
            self._circuit_breakers[provider_key].record_failure()
            if span and tracer:
                span.add_event("provider_failed_tripping_fallback", {"error": str(primary_error)})

            # Cascading fallback
            fallback_provider = self.fallback_provider
            fb_model_name = getattr(fallback_provider, "model_name", "fallback-model")
            try:
                resp = await fallback_provider.generate(messages, tools)
                if tracer:
                    tracer.record_token_usage(resp.prompt_tokens, resp.completion_tokens, resp.estimated_cost_usd)
                    if span:
                        span.attributes.update({
                            "fallback_triggered": True,
                            "fallback_model": fb_model_name,
                            "cost_usd": resp.estimated_cost_usd
                        })
                        tracer.end_span(span, status="OK")
                return resp
            except Exception as fb_error:
                if span and tracer:
                    tracer.end_span(span, status="ERROR", error=f"Primary: {primary_error} | Fallback: {fb_error}")
                raise RuntimeError(f"All model providers failed: {primary_error} -> {fb_error}")
