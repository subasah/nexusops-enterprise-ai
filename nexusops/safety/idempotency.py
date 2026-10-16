"""
NexusOps Enterprise Idempotency & Deduplication Engine.

Guarantees that retry storms, network timeouts, or repeated agent tool loops
never execute duplicate mutations or financial side-effects.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class IdempotencyRecord:
    key: str
    tool_name: str
    payload_hash: str
    status: IdempotencyStatus
    response: Optional[Any] = None
    created_at: float = 0.0
    completed_at: Optional[float] = None


class IdempotencyEngine:
    """Manages transactional idempotency across tool executions."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._records: Dict[str, IdempotencyRecord] = {}

    @staticmethod
    def compute_hash(tool_name: str, arguments: Dict[str, Any], explicit_key: Optional[str] = None) -> str:
        if explicit_key:
            return explicit_key
        # Canonical JSON string representation for stable hashing
        canonical_payload = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()[:16]

    def acquire(self, tool_name: str, arguments: Dict[str, Any], explicit_key: Optional[str] = None) -> tuple[bool, str, Optional[Any]]:
        """
        Attempts to acquire execution rights for this tool call.
        Returns: (can_execute: bool, idempotency_key: str, cached_result: Optional[Any])
        """
        key = self.compute_hash(tool_name, arguments, explicit_key)
        now = time.time()

        if key in self._records:
            rec = self._records[key]
            # Check TTL
            if now - rec.created_at < self.ttl_seconds:
                if rec.status == IdempotencyStatus.COMPLETED:
                    return False, key, rec.response
                elif rec.status == IdempotencyStatus.IN_PROGRESS:
                    # Ongoing call - protect against concurrent execution
                    return False, key, {"status": "concurrent_execution_in_progress", "key": key}

        # Register new in-progress execution
        payload_hash = hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
        self._records[key] = IdempotencyRecord(
            key=key,
            tool_name=tool_name,
            payload_hash=payload_hash,
            status=IdempotencyStatus.IN_PROGRESS,
            created_at=now
        )
        return True, key, None

    def commit(self, key: str, response: Any) -> None:
        if key in self._records:
            self._records[key].status = IdempotencyStatus.COMPLETED
            self._records[key].response = response
            self._records[key].completed_at = time.time()

    def abort(self, key: str, error: str) -> None:
        if key in self._records:
            self._records[key].status = IdempotencyStatus.FAILED
            self._records[key].response = {"error": error}
            self._records[key].completed_at = time.time()

    def get_record(self, key: str) -> Optional[IdempotencyRecord]:
        return self._records.get(key)
