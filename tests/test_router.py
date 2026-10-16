"""
Unit Tests for Model Router, Semantic Caching, and Circuit Breakers.
"""

import pytest
from nexusops.routing.cache import PromptCache
from nexusops.routing.providers.base import LLMResponse
from nexusops.routing.providers.mock_provider import MockLLMProvider
from nexusops.routing.router import CircuitBreakerState, ModelRouter, RoutingPolicy


def test_prompt_cache():
    cache = PromptCache(ttl_seconds=60)
    messages = [{"role": "user", "content": "Hello"}]
    key = cache.compute_key(messages, None, "test-model")

    assert cache.get(key) is None
    resp = LLMResponse(content="World", prompt_tokens=2, completion_tokens=1)
    cache.set(key, resp)

    hit = cache.get(key)
    assert hit is not None
    assert hit.content == "World"
    assert cache.stats()["hits"] == 1


@pytest.mark.asyncio
async def test_router_circuit_breaker_and_fallback():
    # Flaky primary that throws error
    flaky_primary = MockLLMProvider(model_name="flaky-primary", should_fail=True)
    resilient_fallback = MockLLMProvider(model_name="reliable-fallback")

    router = ModelRouter(
        reasoning_provider=flaky_primary,
        fallback_provider=resilient_fallback
    )

    # Calling should catch primary failure and gracefully return fallback response
    resp = await router.route_and_generate(
        messages=[{"role": "user", "content": "Check system"}]
    )
    assert resp is not None
    # Verify primary circuit breaker recorded failure
    assert router._circuit_breakers["primary"].failures >= 1
