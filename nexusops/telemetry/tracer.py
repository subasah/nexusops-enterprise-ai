"""
NexusOps Structured Observability & OpenTelemetry-Compatible Tracing System.

Provides high-resolution distributed tracing across LLM calls, tool executions,
and safety evaluation boundaries with token-budget accounting and latency tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SpanKind(str, Enum):
    AGENT = "agent"
    LLM_CALL = "llm_call"
    TOOL_EXECUTION = "tool_execution"
    SAFETY_GUARD = "safety_guard"
    HITL_GATE = "hitl_gate"
    COMPENSATION = "compensation"


@dataclass
class Span:
    span_id: str
    trace_id: str
    name: str
    kind: SpanKind
    start_time: float
    end_time: Optional[float] = None
    parent_span_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "RUNNING"  # "OK", "ERROR", "RUNNING"
    error_message: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return round((end - self.start_time) * 1000, 2)

    def finish(self, status: str = "OK", error: Optional[str] = None) -> None:
        self.end_time = time.time()
        self.status = status
        if error:
            self.error_message = error
            self.status = "ERROR"

    def add_event(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "data": data or {}
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "parent_span_id": self.parent_span_id,
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
            "error_message": self.error_message,
        }


class Tracer:
    """In-memory distributed tracer for LLM agent workflows."""

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.spans: List[Span] = []
        self._active_spans: List[Span] = []
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_estimated_cost_usd: float = 0.0

    def start_span(
        self,
        name: str,
        kind: SpanKind,
        attributes: Optional[Dict[str, Any]] = None,
        parent_span_id: Optional[str] = None
    ) -> Span:
        parent_id = parent_span_id or (self._active_spans[-1].span_id if self._active_spans else None)
        span = Span(
            span_id=str(uuid.uuid4())[:8],
            trace_id=self.trace_id,
            name=name,
            kind=kind,
            start_time=time.time(),
            parent_span_id=parent_id,
            attributes=attributes or {}
        )
        self.spans.append(span)
        self._active_spans.append(span)
        return span

    def end_span(self, span: Span, status: str = "OK", error: Optional[str] = None) -> None:
        span.finish(status=status, error=error)
        if span in self._active_spans:
            self._active_spans.remove(span)

    def record_token_usage(self, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_estimated_cost_usd += cost_usd

    def get_summary(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_count": len(self.spans),
            "total_duration_ms": sum(s.duration_ms for s in self.spans if s.parent_span_id is None) or (
                max([s.duration_ms for s in self.spans], default=0.0)
            ),
            "tokens": {
                "prompt": self.total_prompt_tokens,
                "completion": self.total_completion_tokens,
                "total": self.total_prompt_tokens + self.total_completion_tokens
            },
            "estimated_cost_usd": round(self.total_estimated_cost_usd, 6),
            "spans": [s.to_dict() for s in self.spans]
        }
