"""
NexusOps Enterprise CRM & Customer Support Service.

Simulates a Zendesk/Salesforce ticketing platform with support for priority escalation,
customer communication threads, sentiment tagging, and internal audit notes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CRMMessage:
    sender: str
    message: str
    is_internal: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class CRMTicket:
    ticket_id: str
    customer_id: str
    subject: str
    status: str  # "OPEN", "PENDING_CUSTOMER", "RESOLVED", "ESCALATED"
    priority: str  # "LOW", "NORMAL", "HIGH", "URGENT"
    sentiment: str  # "FRUSTRATED", "NEUTRAL", "SATISFIED"
    messages: List[CRMMessage] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class CRMService:
    """Enterprise ticketing and customer relationship management platform."""

    def __init__(self):
        self._tickets: Dict[str, CRMTicket] = {}
        self.seed_defaults()

    def seed_defaults(self) -> None:
        self._tickets.clear()
        now = time.time()
        t1 = CRMTicket(
            ticket_id="TK-4401",
            customer_id="CUST-901",
            subject="Dispute regarding unrecognized charge on invoice INV-8802 ($189.50)",
            status="OPEN",
            priority="URGENT",
            sentiment="FRUSTRATED",
            tags=["billing_dispute", "vip_customer"],
            created_at=now - 3600 * 4
        )
        t1.messages.append(
            CRMMessage(
                sender="billing@acmeglobal.com",
                message="We noticed an extra charge of $189.50 that we did not authorize on our credit card. Please investigate and refund immediately.",
                is_internal=False,
                timestamp=now - 3600 * 4
            )
        )
        self._tickets["TK-4401"] = t1

        t2 = CRMTicket(
            ticket_id="TK-4402",
            customer_id="CUST-902",
            subject="Enterprise annual renewal reconciliation inquiry",
            status="OPEN",
            priority="HIGH",
            sentiment="NEUTRAL",
            tags=["renewal", "enterprise"],
            created_at=now - 3600 * 8
        )
        self._tickets["TK-4402"] = t2

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        t = self._tickets.get(ticket_id)
        if not t:
            return None
        return {
            "ticket_id": t.ticket_id,
            "customer_id": t.customer_id,
            "subject": t.subject,
            "status": t.status,
            "priority": t.priority,
            "sentiment": t.sentiment,
            "tags": list(t.tags),
            "messages_count": len(t.messages),
            "messages": [
                {
                    "sender": m.sender,
                    "message": m.message,
                    "is_internal": m.is_internal,
                    "timestamp": m.timestamp
                }
                for m in t.messages
            ]
        }

    def get_tickets_for_customer(self, customer_id: str) -> List[Dict[str, Any]]:
        return [
            self.get_ticket(t.ticket_id)
            for t in self._tickets.values()
            if t.customer_id == customer_id
        ]

    def update_ticket_status(self, ticket_id: str, new_status: str) -> Dict[str, Any]:
        if ticket_id not in self._tickets:
            return {"error": f"Ticket `{ticket_id}` not found"}
        old_status = self._tickets[ticket_id].status
        self._tickets[ticket_id].status = new_status
        return {
            "status": "success",
            "ticket_id": ticket_id,
            "previous_status": old_status,
            "current_status": new_status
        }

    def add_internal_note(self, ticket_id: str, note: str, author: str = "nexusops_agent") -> Dict[str, Any]:
        if ticket_id not in self._tickets:
            return {"error": f"Ticket `{ticket_id}` not found"}
        msg = CRMMessage(sender=author, message=note, is_internal=True)
        self._tickets[ticket_id].messages.append(msg)
        return {"status": "success", "ticket_id": ticket_id, "note_recorded": note}

    def send_customer_message(self, ticket_id: str, message: str, sender: str = "NexusOps Support") -> Dict[str, Any]:
        if ticket_id not in self._tickets:
            return {"error": f"Ticket `{ticket_id}` not found"}
        msg = CRMMessage(sender=sender, message=message, is_internal=False)
        self._tickets[ticket_id].messages.append(msg)
        return {"status": "success", "ticket_id": ticket_id, "message_sent": message}
