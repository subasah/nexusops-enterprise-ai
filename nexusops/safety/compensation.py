"""
NexusOps Compensation & Rollback Ledger.

Implements SAGA-pattern two-phase compensation for agentic multi-step mutations.
If a long-horizon task fails halfway through, executed actions are rolled back in LIFO order.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class CompensationStatus(str, Enum):
    REGISTERED = "REGISTERED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class CompensationEntry:
    entry_id: str
    action_name: str
    forward_arguments: Dict[str, Any]
    rollback_tool_name: str
    rollback_arguments: Dict[str, Any]
    status: CompensationStatus = CompensationStatus.REGISTERED
    registered_at: float = 0.0
    executed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class CompensationLedger:
    """Maintains a stack of compensation actions for transactional safety."""

    def __init__(self):
        self._stack: List[CompensationEntry] = []
        self._history: List[CompensationEntry] = []

    def register(
        self,
        action_name: str,
        forward_arguments: Dict[str, Any],
        rollback_tool_name: str,
        rollback_arguments: Dict[str, Any]
    ) -> CompensationEntry:
        entry = CompensationEntry(
            entry_id=str(uuid.uuid4())[:8],
            action_name=action_name,
            forward_arguments=forward_arguments,
            rollback_tool_name=rollback_tool_name,
            rollback_arguments=rollback_arguments,
            status=CompensationStatus.REGISTERED,
            registered_at=time.time()
        )
        self._stack.append(entry)
        self._history.append(entry)
        return entry

    async def rollback_all(self, tool_executor: Callable[[str, Dict[str, Any]], Any]) -> List[Dict[str, Any]]:
        """Executes compensation actions in reverse chronological order (LIFO)."""
        rollback_results = []
        while self._stack:
            entry = self._stack.pop()
            try:
                # Execute rollback tool call
                res = await tool_executor(entry.rollback_tool_name, entry.rollback_arguments)
                entry.status = CompensationStatus.EXECUTED
                entry.executed_at = time.time()
                entry.result = res
                rollback_results.append({
                    "entry_id": entry.entry_id,
                    "action_rolled_back": entry.action_name,
                    "rollback_tool": entry.rollback_tool_name,
                    "status": "SUCCESS",
                    "result": res
                })
            except Exception as e:
                entry.status = CompensationStatus.FAILED
                entry.executed_at = time.time()
                entry.error = str(e)
                rollback_results.append({
                    "entry_id": entry.entry_id,
                    "action_rolled_back": entry.action_name,
                    "rollback_tool": entry.rollback_tool_name,
                    "status": "FAILED",
                    "error": str(e)
                })
        return rollback_results

    def clear(self) -> None:
        """Called when workflow succeeds completely and no rollbacks are needed."""
        self._stack.clear()

    @property
    def pending_count(self) -> int:
        return len(self._stack)

    def get_history(self) -> List[Dict[str, Any]]:
        return [
            {
                "entry_id": e.entry_id,
                "action": e.action_name,
                "rollback_tool": e.rollback_tool_name,
                "status": e.status.value,
                "registered_at": e.registered_at,
                "executed_at": e.executed_at,
                "error": e.error
            }
            for e in self._history
        ]
