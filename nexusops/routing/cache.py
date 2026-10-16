"""
NexusOps Semantic & Exact Hash Prompt Cache.

Deduplicates identical prompt invocations, saving latency and token costs.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from nexusops.routing.providers.base import LLMResponse


@dataclass
class CacheEntry:
    key: str
    response: LLMResponse
    created_at: float
    hit_count: int = 0


class PromptCache:
    """In-memory LRU prompt cache with TTL expiration."""

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: Dict[str, CacheEntry] = {}
        self.total_hits: int = 0
        self.total_misses: int = 0

    @staticmethod
    def compute_key(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]], model_name: str) -> str:
        payload = {
            "model": model_name,
            "messages": messages,
            "tools": tools or []
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[LLMResponse]:
        now = time.time()
        entry = self._entries.get(key)
        if not entry:
            self.total_misses += 1
            return None

        if now - entry.created_at > self.ttl_seconds:
            del self._entries[key]
            self.total_misses += 1
            return None

        entry.hit_count += 1
        self.total_hits += 1
        return entry.response

    def set(self, key: str, response: LLMResponse) -> None:
        if len(self._entries) >= self.max_entries:
            # Evict oldest
            oldest_key = min(self._entries, key=lambda k: self._entries[k].created_at)
            del self._entries[oldest_key]

        self._entries[key] = CacheEntry(
            key=key,
            response=response,
            created_at=time.time()
        )

    def stats(self) -> Dict[str, Any]:
        total = self.total_hits + self.total_misses
        hit_rate = (self.total_hits / total) if total > 0 else 0.0
        return {
            "entries_count": len(self._entries),
            "hits": self.total_hits,
            "misses": self.total_misses,
            "hit_rate_pct": round(hit_rate * 100, 1)
        }
