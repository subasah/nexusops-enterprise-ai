"""
NexusOps Enterprise Payment Gateway Integration.

Simulates a Stripe/Fintech payment processor with charge inquiry, idempotent refunds,
dispute workflows, and programmatic failure injection for resilience testing.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Charge:
    charge_id: str
    customer_id: str
    order_id: str
    amount: float
    currency: str
    status: str  # "captured", "refunded", "partially_refunded"
    refunded_amount: float = 0.0
    disputed: bool = False
    dispute_reason: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class PaymentGatewayService:
    """Enterprise payment gateway simulation with realistic constraints."""

    def __init__(self):
        self._charges: Dict[str, Charge] = {}
        self._refund_history: List[Dict[str, Any]] = []
        self._simulate_failure: bool = False
        self.seed_defaults()

    def seed_defaults(self) -> None:
        self._charges.clear()
        self._refund_history.clear()
        self._simulate_failure = False

        now = time.time()
        self._charges["ch_7701"] = Charge(
            charge_id="ch_7701",
            customer_id="CUST-901",
            order_id="ORD-7701",
            amount=1450.00,
            currency="USD",
            status="captured",
            created_at=now - 86400 * 2
        )
        self._charges["ch_7702"] = Charge(
            charge_id="ch_7702",
            customer_id="CUST-901",
            order_id="ORD-7702",
            amount=189.50,
            currency="USD",
            status="captured",
            disputed=True,
            dispute_reason="unrecognized_charge",
            created_at=now - 86400 * 1
        )
        self._charges["ch_7703"] = Charge(
            charge_id="ch_7703",
            customer_id="CUST-902",
            order_id="ORD-7703",
            amount=5200.00,
            currency="USD",
            status="captured",
            created_at=now - 86400 * 5
        )
        self._charges["ch_7704"] = Charge(
            charge_id="ch_7704",
            customer_id="CUST-903",
            order_id="ORD-7704",
            amount=75.00,
            currency="USD",
            status="captured",
            created_at=now - 86400 * 3
        )

    def set_failure_injection(self, enabled: bool) -> None:
        """Enables artificial failure for testing circuit-breakers and compensation."""
        self._simulate_failure = enabled

    def get_charge_details(self, charge_id: str) -> Dict[str, Any]:
        if charge_id not in self._charges:
            return {"error": f"Charge `{charge_id}` not found on payment gateway."}
        c = self._charges[charge_id]
        return {
            "charge_id": c.charge_id,
            "customer_id": c.customer_id,
            "order_id": c.order_id,
            "amount": c.amount,
            "currency": c.currency,
            "status": c.status,
            "refunded_amount": c.refunded_amount,
            "disputed": c.disputed,
            "dispute_reason": c.dispute_reason,
        }

    def find_charge_by_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        for c in self._charges.values():
            if c.order_id == order_id:
                return self.get_charge_details(c.charge_id)
        return None

    def issue_refund(
        self,
        charge_id: str,
        amount: float,
        reason: str = "customer_dispute",
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if self._simulate_failure:
            raise RuntimeError("PaymentGatewayServiceError: 503 Service Unavailable (Network partition)")

        if charge_id not in self._charges:
            return {"error": f"Charge `{charge_id}` does not exist"}

        charge = self._charges[charge_id]
        remaining = charge.amount - charge.refunded_amount

        if amount <= 0:
            return {"error": f"Invalid refund amount: ${amount:.2f}"}

        if amount > remaining:
            return {
                "error": f"Refund amount ${amount:.2f} exceeds remaining refundable balance ${remaining:.2f}"
            }

        charge.refunded_amount += amount
        if charge.refunded_amount >= charge.amount:
            charge.status = "refunded"
        else:
            charge.status = "partially_refunded"

        refund_id = f"ref_{uuid.uuid4().hex[:8]}"
        record = {
            "refund_id": refund_id,
            "charge_id": charge_id,
            "amount": amount,
            "reason": reason,
            "timestamp": time.time(),
            "idempotency_key": idempotency_key
        }
        self._refund_history.append(record)

        return {
            "status": "succeeded",
            "refund_id": refund_id,
            "charge_id": charge_id,
            "amount_refunded": amount,
            "new_charge_status": charge.status,
            "remaining_balance": charge.amount - charge.refunded_amount
        }

    def reverse_refund(self, charge_id: str, amount: float) -> Dict[str, Any]:
        """Compensation hook: reverses a prior refund if an downstream operation aborted."""
        if charge_id not in self._charges:
            return {"error": f"Charge `{charge_id}` does not exist"}

        charge = self._charges[charge_id]
        charge.refunded_amount = max(0.0, charge.refunded_amount - amount)
        if charge.refunded_amount == 0.0:
            charge.status = "captured"
        else:
            charge.status = "partially_refunded"

        return {
            "status": "reversed",
            "charge_id": charge_id,
            "amount_reversed": amount,
            "new_charge_status": charge.status
        }
