"""
Unit & Integration Tests for Enterprise Subsystems.
"""

import pytest
from nexusops.integrations.database import DatabaseService
from nexusops.integrations.payment_gateway import PaymentGatewayService
from nexusops.integrations.crm_service import CRMService
from nexusops.integrations.infrastructure import InfrastructureService


def test_database_crud_and_audit():
    db = DatabaseService(":memory:")
    # Read customer
    cust = db.get_customer_by_id("CUST-901")
    assert cust is not None
    assert cust["tier"] == "VIP"

    # Read invoice
    inv = db.get_invoice_by_id("INV-8802")
    assert inv is not None
    assert inv["amount_usd"] == 189.50

    # Audit log test
    db.update_order_status("ORD-7702", "REFUNDED", actor="test_agent")
    logs = db.get_audit_logs()
    assert len(logs) > 0
    assert logs[0]["action"] == "UPDATE_ORDER_STATUS"


def test_payment_gateway_refund_and_balance():
    payment = PaymentGatewayService()
    charge = payment.get_charge_details("ch_7702")
    assert charge["amount"] == 189.50
    assert charge["disputed"] is True

    # Successful refund
    res = payment.issue_refund("ch_7702", 189.50, reason="test_refund")
    assert res["status"] == "succeeded"
    assert res["remaining_balance"] == 0.0

    # Exceed balance
    res_err = payment.issue_refund("ch_7702", 50.0)
    assert "error" in res_err

    # Reverse refund (compensation hook)
    rev = payment.reverse_refund("ch_7702", 189.50)
    assert rev["status"] == "reversed"
    charge_after = payment.get_charge_details("ch_7702")
    assert charge_after["refunded_amount"] == 0.0


def test_crm_service_thread():
    crm = CRMService()
    ticket = crm.get_ticket("TK-4401")
    assert ticket is not None
    assert ticket["priority"] == "URGENT"

    crm.add_internal_note("TK-4401", "Investigation completed", author="agent")
    crm.update_ticket_status("TK-4401", "RESOLVED")

    updated = crm.get_ticket("TK-4401")
    assert updated["status"] == "RESOLVED"
    assert updated["messages_count"] == 2


def test_infrastructure_dlq():
    infra = InfrastructureService()
    msgs = infra.get_dlq_messages(status_filter="DEAD")
    assert len(msgs) == 1
    assert msgs[0]["message_id"] == "dlq_msg_101"

    replay = infra.replay_dlq_message("dlq_msg_101")
    assert replay["status"] == "success"
    health = infra.inspect_system_health()
    assert health["unresolved_dlq_count"] == 0
