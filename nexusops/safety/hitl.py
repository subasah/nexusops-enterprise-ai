"""
NexusOps Human-In-The-Loop (HITL) Gatekeeper & Action Risk Classification.

Enforces cryptographic approval challenges for high-risk, irreversible,
or financial actions (refunds, ledger adjustments, account deletions).
"""

from __future__ import annotations

import hmac
import hashlib
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskTier(str, Enum):
    TIER_1_READ_ONLY = "TIER_1_READ_ONLY"          # Zero-risk reads, search, status checks
    TIER_2_REVERSIBLE = "TIER_2_REVERSIBLE"        # Low-risk mutations with rollback capability (ticket notes, tags)
    TIER_3_CRITICAL_FINANCIAL = "TIER_3_CRITICAL"   # High-risk financial, ledger, destructive (refunds > limit, deletes)


class ChallengeStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class PendingChallenge:
    challenge_token: str
    tool_name: str
    arguments: Dict[str, Any]
    risk_tier: RiskTier
    reason: str
    impact_summary: str
    status: ChallengeStatus = ChallengeStatus.PENDING
    approver: Optional[str] = None
    created_at: float = 0.0
    decided_at: Optional[float] = None


class HITLGatekeeper:
    """Enforces policy-driven approval workflows for agent actions."""

    def __init__(self, secret_key: str = "nexusops-secret-key-prod-994", auto_refund_limit_usd: float = 200.0):
        self.secret_key = secret_key
        self.auto_refund_limit_usd = auto_refund_limit_usd
        self._challenges: Dict[str, PendingChallenge] = {}

    def classify_action(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[RiskTier, str]:
        """Classifies the risk of an action based on tool definition and runtime arguments."""
        if tool_name in ["read_customer_by_id", "read_customer_by_email", "query_database_orders", "get_charge_details", "get_dlq_messages", "inspect_system_health"]:
            return RiskTier.TIER_1_READ_ONLY, "Safe read-only operation"

        if tool_name in ["update_crm_ticket", "add_crm_internal_note", "replay_webhook"]:
            return RiskTier.TIER_2_REVERSIBLE, "Reversible operational modification"

        if tool_name in ["issue_refund"]:
            amount = float(arguments.get("amount", 0.0))
            if amount > self.auto_refund_limit_usd:
                return (
                    RiskTier.TIER_3_CRITICAL_FINANCIAL,
                    f"Refund amount ${amount:.2f} exceeds automatic threshold of ${self.auto_refund_limit_usd:.2f}."
                )
            return RiskTier.TIER_2_REVERSIBLE, f"Refund amount ${amount:.2f} is within automated tolerance."

        if tool_name in ["delete_customer_record", "execute_sql_mutation", "cancel_subscription_override"]:
            return RiskTier.TIER_3_CRITICAL_FINANCIAL, f"Critical destructive operation on enterprise system: {tool_name}"

        return RiskTier.TIER_2_REVERSIBLE, "Standard action"

    def requires_approval(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, Optional[PendingChallenge]]:
        risk, reason = self.classify_action(tool_name, arguments)
        if risk != RiskTier.TIER_3_CRITICAL_FINANCIAL:
            return False, None

        # Create cryptographic challenge token
        raw_seed = f"{tool_name}:{uuid.uuid4()}:{time.time()}"
        token = hmac.new(self.secret_key.encode(), raw_seed.encode(), hashlib.sha256).hexdigest()[:16]

        impact_summary = (
            f"Action: `{tool_name}` with args {arguments}. "
            f"Requires Tier-3 Financial/Security authorization."
        )

        challenge = PendingChallenge(
            challenge_token=token,
            tool_name=tool_name,
            arguments=arguments,
            risk_tier=risk,
            reason=reason,
            impact_summary=impact_summary,
            status=ChallengeStatus.PENDING,
            created_at=time.time()
        )
        self._challenges[token] = challenge
        return True, challenge

    def approve(self, token: str, approver: str = "ops_supervisor") -> tuple[bool, str]:
        if token not in self._challenges:
            return False, "Challenge token not found"
        challenge = self._challenges[token]
        if challenge.status != ChallengeStatus.PENDING:
            return False, f"Challenge is already {challenge.status}"

        challenge.status = ChallengeStatus.APPROVED
        challenge.approver = approver
        challenge.decided_at = time.time()
        return True, "Challenge successfully approved"

    def reject(self, token: str, reason: str = "Rejected by operator", approver: str = "ops_supervisor") -> tuple[bool, str]:
        if token not in self._challenges:
            return False, "Challenge token not found"
        challenge = self._challenges[token]
        if challenge.status != ChallengeStatus.PENDING:
            return False, f"Challenge is already {challenge.status}"

        challenge.status = ChallengeStatus.REJECTED
        challenge.reason += f" | Rejected: {reason}"
        challenge.approver = approver
        challenge.decided_at = time.time()
        return True, "Challenge rejected"

    def get_challenge(self, token: str) -> Optional[PendingChallenge]:
        return self._challenges.get(token)

    def list_pending_challenges(self) -> List[PendingChallenge]:
        return [c for c in self._challenges.values() if c.status == ChallengeStatus.PENDING]
