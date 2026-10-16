"""
NexusOps Unified Enterprise Tool Registry.

Exposes safe, validated, and observable tool interfaces to model providers,
enforcing schema contracts, action risk tiering, idempotency, and compensation registration.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from nexusops.integrations.crm_service import CRMService
from nexusops.integrations.database import DatabaseService
from nexusops.integrations.infrastructure import InfrastructureService
from nexusops.integrations.payment_gateway import PaymentGatewayService
from nexusops.safety.compensation import CompensationLedger
from nexusops.safety.hitl import HITLGatekeeper, RiskTier
from nexusops.safety.idempotency import IdempotencyEngine
from nexusops.telemetry.tracer import SpanKind, Tracer


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    handler: Callable[..., Any]
    risk_tier: RiskTier
    category: str
    requires_idempotency: bool = False
    compensation_tool: Optional[str] = None


class ToolRegistry:
    """Registry and execution orchestrator for enterprise tools."""

    def __init__(
        self,
        db: DatabaseService,
        payment: PaymentGatewayService,
        crm: CRMService,
        infra: InfrastructureService,
        idempotency: IdempotencyEngine,
        hitl: HITLGatekeeper,
        compensation: CompensationLedger,
    ):
        self.db = db
        self.payment = payment
        self.crm = crm
        self.infra = infra
        self.idempotency = idempotency
        self.hitl = hitl
        self.compensation = compensation
        self._tools: Dict[str, ToolDefinition] = {}

        self._register_all_tools()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_schemas_for_llm(self) -> List[Dict[str, Any]]:
        """Returns OpenAPI/JSON schemas formatted for OpenAI / Anthropic / Gemini tool calling."""
        schemas = []
        for t in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": f"[{t.risk_tier.value}] {t.description}",
                    "parameters": t.parameters_schema
                }
            })
        return schemas

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tracer: Optional[Tracer] = None,
        bypass_hitl_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a registered tool under full safety, telemetry, and idempotency guarantees.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return {"error": f"Tool `{tool_name}` is not registered in ToolRegistry"}

        span = None
        if tracer:
            span = tracer.start_span(
                name=f"tool:{tool_name}",
                kind=SpanKind.TOOL_EXECUTION,
                attributes={"tool_name": tool_name, "risk_tier": tool.risk_tier.value, "arguments": arguments}
            )

        # 1. HITL Check for Tier-3 Critical Actions
        if tool.risk_tier == RiskTier.TIER_3_CRITICAL_FINANCIAL:
            # If a valid approved token was not provided, check or trigger challenge
            if bypass_hitl_token:
                challenge = self.hitl.get_challenge(bypass_hitl_token)
                if not challenge or challenge.status.value != "APPROVED":
                    if span and tracer:
                        tracer.end_span(span, status="ERROR", error="Unapproved HITL token")
                    return {
                        "status": "APPROVAL_REQUIRED",
                        "error": "Provided HITL authorization token is invalid or unapproved."
                    }
            else:
                needs_approval, challenge = self.hitl.requires_approval(tool_name, arguments)
                if needs_approval and challenge:
                    if span and tracer:
                        tracer.end_span(span, status="PAUSED", error="Requires human authorization")
                    return {
                        "status": "APPROVAL_REQUIRED",
                        "challenge_token": challenge.challenge_token,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "reason": challenge.reason,
                        "impact_summary": challenge.impact_summary
                    }

        # 2. Idempotency Check for Mutations
        idempotency_key = arguments.get("idempotency_key")
        can_execute = True
        computed_key = None
        cached_result = None

        if tool.requires_idempotency:
            can_execute, computed_key, cached_result = self.idempotency.acquire(
                tool_name=tool_name,
                arguments=arguments,
                explicit_key=idempotency_key
            )
            if not can_execute:
                if span and tracer:
                    span.add_event("idempotency_cache_hit", {"key": computed_key})
                    tracer.end_span(span, status="OK")
                return {
                    "status": "idempotent_replay",
                    "idempotency_key": computed_key,
                    "result": cached_result
                }

        # 3. Invocation
        try:
            handler = tool.handler
            if inspect.iscoroutinefunction(handler):
                result = await handler(**arguments)
            else:
                result = handler(**arguments)

            # Commit idempotency
            if tool.requires_idempotency and computed_key:
                self.idempotency.commit(computed_key, result)

            # Register compensation rollback if reversible mutation
            if tool.risk_tier in [RiskTier.TIER_2_REVERSIBLE, RiskTier.TIER_3_CRITICAL_FINANCIAL]:
                self._register_compensation_hook(tool, arguments, result)

            if span and tracer:
                tracer.end_span(span, status="OK")

            return {"status": "success", "result": result}

        except Exception as e:
            if tool.requires_idempotency and computed_key:
                self.idempotency.abort(computed_key, str(e))
            if span and tracer:
                tracer.end_span(span, status="ERROR", error=str(e))
            return {"status": "error", "error": str(e)}

    def _register_compensation_hook(self, tool: ToolDefinition, args: Dict[str, Any], result: Any) -> None:
        """Configures automated compensation actions for reversible mutations."""
        if tool.name == "issue_refund" and isinstance(result, dict) and result.get("status") == "succeeded":
            self.compensation.register(
                action_name="issue_refund",
                forward_arguments=args,
                rollback_tool_name="reverse_refund",
                rollback_arguments={"charge_id": args["charge_id"], "amount": args["amount"]}
            )
        elif tool.name == "update_crm_ticket" and isinstance(result, dict) and "previous_status" in result:
            self.compensation.register(
                action_name="update_crm_ticket",
                forward_arguments=args,
                rollback_tool_name="update_crm_ticket",
                rollback_arguments={"ticket_id": args["ticket_id"], "new_status": result["previous_status"]}
            )

    def _register_all_tools(self) -> None:
        """Binds enterprise services to typed tool interfaces."""

        # 1. Database: read_customer_by_id
        self.register(ToolDefinition(
            name="read_customer_by_id",
            description="Fetch enterprise customer profile, VIP status, and account balance by customer ID.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "The customer ID (e.g., CUST-901)"}
                },
                "required": ["customer_id"]
            },
            handler=self.db.get_customer_by_id,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="DATABASE"
        ))

        # 2. Database: read_customer_by_email
        self.register(ToolDefinition(
            name="read_customer_by_email",
            description="Find enterprise customer profile by primary email address.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer contact email address"}
                },
                "required": ["email"]
            },
            handler=self.db.get_customer_by_email,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="DATABASE"
        ))

        # 3. Database: query_orders_by_customer
        self.register(ToolDefinition(
            name="query_orders_by_customer",
            description="Retrieve all historical order records and statuses for a given customer.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "The customer ID (e.g. CUST-901)"}
                },
                "required": ["customer_id"]
            },
            handler=self.db.get_orders_by_customer,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="DATABASE"
        ))

        # 4. Database: get_invoice_by_id
        self.register(ToolDefinition(
            name="get_invoice_by_id",
            description="Look up invoice details, linked order ID, amount, and payment status.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string", "description": "Invoice reference ID (e.g. INV-8802)"}
                },
                "required": ["invoice_id"]
            },
            handler=self.db.get_invoice_by_id,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="DATABASE"
        ))

        # 5. Payment Gateway: get_charge_details
        self.register(ToolDefinition(
            name="get_charge_details",
            description="Inspect payment processor charge record, dispute state, and refundable balance.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "charge_id": {"type": "string", "description": "Gateway charge ID (e.g. ch_7702)"}
                },
                "required": ["charge_id"]
            },
            handler=self.payment.get_charge_details,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="PAYMENT"
        ))

        # 6. Payment Gateway: find_charge_by_order
        self.register(ToolDefinition(
            name="find_charge_by_order",
            description="Find the payment processor charge associated with an order ID.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order reference ID (e.g. ORD-7702)"}
                },
                "required": ["order_id"]
            },
            handler=self.payment.find_charge_by_order,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="PAYMENT"
        ))

        # 7. Payment Gateway: issue_refund
        self.register(ToolDefinition(
            name="issue_refund",
            description="Issue a full or partial refund for a charge. Transactions > $200 require human authorization.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "charge_id": {"type": "string", "description": "The gateway charge identifier (e.g., ch_7702)"},
                    "amount": {"type": "number", "description": "Dollar amount to refund"},
                    "reason": {"type": "string", "description": "Justification for refund", "default": "customer_dispute"},
                    "idempotency_key": {"type": "string", "description": "Unique key to ensure transaction idempotency"}
                },
                "required": ["charge_id", "amount"]
            },
            handler=self.payment.issue_refund,
            risk_tier=RiskTier.TIER_3_CRITICAL_FINANCIAL,
            category="PAYMENT",
            requires_idempotency=True,
            compensation_tool="reverse_refund"
        ))

        # 8. Payment Gateway: reverse_refund (Internal compensation)
        self.register(ToolDefinition(
            name="reverse_refund",
            description="Internal compensation tool: Reverses a refund if a downstream step fails.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "charge_id": {"type": "string", "description": "The charge ID"},
                    "amount": {"type": "number", "description": "Amount to reverse"}
                },
                "required": ["charge_id", "amount"]
            },
            handler=self.payment.reverse_refund,
            risk_tier=RiskTier.TIER_2_REVERSIBLE,
            category="PAYMENT"
        ))

        # 9. CRM: get_ticket
        self.register(ToolDefinition(
            name="get_crm_ticket",
            description="Retrieve support ticket details, conversation history, customer sentiment, and tags.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "CRM Ticket ID (e.g., TK-4401)"}
                },
                "required": ["ticket_id"]
            },
            handler=self.crm.get_ticket,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="CRM"
        ))

        # 10. CRM: update_crm_ticket
        self.register(ToolDefinition(
            name="update_crm_ticket",
            description="Update the status of an existing CRM ticket (OPEN, RESOLVED, ESCALATED).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Ticket ID"},
                    "new_status": {"type": "string", "description": "Status (e.g., RESOLVED, ESCALATED)"}
                },
                "required": ["ticket_id", "new_status"]
            },
            handler=self.crm.update_ticket_status,
            risk_tier=RiskTier.TIER_2_REVERSIBLE,
            category="CRM",
            requires_idempotency=True
        ))

        # 11. CRM: add_crm_internal_note
        self.register(ToolDefinition(
            name="add_crm_internal_note",
            description="Add an internal audit note to a support ticket for team visibility.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Ticket ID"},
                    "note": {"type": "string", "description": "Audit or resolution note"}
                },
                "required": ["ticket_id", "note"]
            },
            handler=self.crm.add_internal_note,
            risk_tier=RiskTier.TIER_2_REVERSIBLE,
            category="CRM"
        ))

        # 12. CRM: send_customer_message
        self.register(ToolDefinition(
            name="send_customer_message",
            description="Send an official email / message update to the customer on a support ticket.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Ticket ID"},
                    "message": {"type": "string", "description": "Customer message body"}
                },
                "required": ["ticket_id", "message"]
            },
            handler=self.crm.send_customer_message,
            risk_tier=RiskTier.TIER_2_REVERSIBLE,
            category="CRM"
        ))

        # 13. Infrastructure: get_dlq_messages
        self.register(ToolDefinition(
            name="get_dlq_messages",
            description="Inspect dropped webhook and dead-letter queue messages for system failures.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "status_filter": {"type": "string", "description": "Filter by status ('DEAD', 'REPLAYED')"}
                }
            },
            handler=self.infra.get_dlq_messages,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="INFRASTRUCTURE"
        ))

        # 14. Infrastructure: replay_dlq_message
        self.register(ToolDefinition(
            name="replay_dlq_message",
            description="Replay a dead-letter queue message back to the event bus.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The DLQ message identifier"}
                },
                "required": ["message_id"]
            },
            handler=self.infra.replay_dlq_message,
            risk_tier=RiskTier.TIER_2_REVERSIBLE,
            category="INFRASTRUCTURE"
        ))

        # 15. Infrastructure: inspect_system_health
        self.register(ToolDefinition(
            name="inspect_system_health",
            description="Check health of enterprise backend systems, databases, and message brokers.",
            parameters_schema={"type": "object", "properties": {}},
            handler=self.infra.inspect_system_health,
            risk_tier=RiskTier.TIER_1_READ_ONLY,
            category="INFRASTRUCTURE"
        ))
