"""
NexusOps Typed Agent State & Checkpointing Model.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from nexusops.safety.hitl import PendingChallenge
from nexusops.telemetry.tracer import Tracer


class AgentStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    PLANNING = "PLANNING"
    EXECUTING_TOOLS = "EXECUTING_TOOLS"
    PAUSED_FOR_APPROVAL = "PAUSED_FOR_APPROVAL"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class AgentState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_prompt: str = ""
    status: AgentStatus = AgentStatus.INITIALIZED
    messages: List[Dict[str, Any]] = field(default_factory=list)
    plan_steps: List[str] = field(default_factory=list)
    current_step: int = 0
    tool_observations: List[Dict[str, Any]] = field(default_factory=list)
    pending_challenge: Optional[PendingChallenge] = None
    final_response: Optional[str] = None
    grounding_report: Optional[Dict[str, Any]] = None
    rollback_log: List[Dict[str, Any]] = field(default_factory=list)
    tracer: Optional[Tracer] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None

    def add_message(self, role: str, content: Optional[str], **kwargs: Any) -> None:
        msg: Dict[str, Any] = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_prompt": self.task_prompt,
            "status": self.status.value,
            "plan_steps": self.plan_steps,
            "current_step": self.current_step,
            "messages_count": len(self.messages),
            "tool_observations_count": len(self.tool_observations),
            "has_pending_challenge": self.pending_challenge is not None,
            "pending_challenge": {
                "token": self.pending_challenge.challenge_token,
                "tool": self.pending_challenge.tool_name,
                "args": self.pending_challenge.arguments,
                "reason": self.pending_challenge.reason,
            } if self.pending_challenge else None,
            "final_response": self.final_response,
            "grounding_report": self.grounding_report,
            "rollback_log": self.rollback_log,
            "telemetry": self.tracer.get_summary() if self.tracer else None,
            "error": self.error,
        }
