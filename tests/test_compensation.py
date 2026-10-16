"""
Unit Tests for Idempotency, HITL Gatekeeping, and SAGA Compensation.
"""

import pytest
from nexusops.safety.compensation import CompensationLedger
from nexusops.safety.hitl import ChallengeStatus, HITLGatekeeper, RiskTier
from nexusops.safety.idempotency import IdempotencyEngine, IdempotencyStatus


def test_idempotency_engine():
    engine = IdempotencyEngine()
    can_exec, key, _ = engine.acquire("issue_refund", {"charge_id": "ch_7702", "amount": 100})
    assert can_exec is True

    # Concurrent or duplicate acquisition fails
    can_exec2, key2, _ = engine.acquire("issue_refund", {"charge_id": "ch_7702", "amount": 100})
    assert can_exec2 is False

    # Commit execution
    engine.commit(key, {"status": "succeeded", "refund_id": "ref_123"})

    # Subsequent acquisition returns cached completed response
    can_exec3, _, cached = engine.acquire("issue_refund", {"charge_id": "ch_7702", "amount": 100})
    assert can_exec3 is False
    assert cached["refund_id"] == "ref_123"


def test_hitl_risk_tiering_and_challenge():
    hitl = HITLGatekeeper(auto_refund_limit_usd=200.0)

    # Low-risk action (under $200)
    needs_appr, chal = hitl.requires_approval("issue_refund", {"amount": 189.50})
    assert needs_appr is False

    # High-risk action (over $200)
    needs_appr2, chal2 = hitl.requires_approval("issue_refund", {"amount": 1450.00})
    assert needs_appr2 is True
    assert chal2 is not None
    assert chal2.status == ChallengeStatus.PENDING

    # Approve challenge
    ok, msg = hitl.approve(chal2.challenge_token, approver="security_lead")
    assert ok is True
    assert chal2.status == ChallengeStatus.APPROVED


@pytest.mark.asyncio
async def test_saga_compensation_rollback():
    ledger = CompensationLedger()
    ledger.register(
        action_name="action_step_1",
        forward_arguments={"id": 1},
        rollback_tool_name="undo_step_1",
        rollback_arguments={"id": 1}
    )
    ledger.register(
        action_name="action_step_2",
        forward_arguments={"id": 2},
        rollback_tool_name="undo_step_2",
        rollback_arguments={"id": 2}
    )

    executed_rollbacks = []

    async def mock_executor(tool_name, args):
        executed_rollbacks.append(tool_name)
        return {"status": "ok"}

    results = await ledger.rollback_all(mock_executor)

    # Verifies LIFO order (step 2 rolled back first, then step 1)
    assert executed_rollbacks == ["undo_step_2", "undo_step_1"]
    assert len(results) == 2
    assert ledger.pending_count == 0
