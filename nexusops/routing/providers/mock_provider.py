"""
NexusOps High-Fidelity Mock LLM Provider.

Simulates frontier multi-step reasoning models (e.g. Claude 3.7 Sonnet, GPT-4o, Gemini 1.5 Pro)
with deterministic tool-calling, chain-of-thought scratchpads, latency simulation, and failure modes.
Enables offline development, instant test execution, and deterministic CI/CD pipelines.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional

from nexusops.routing.providers.base import BaseLLMProvider, LLMResponse, ToolCallRequest


class MockLLMProvider(BaseLLMProvider):
    """Deterministic offline LLM simulator."""

    def __init__(
        self,
        model_name: str = "mock-deep-reasoner",
        cost_per_1k_input: float = 0.003,
        cost_per_1k_output: float = 0.015,
        simulated_latency_ms: float = 30.0,
        should_fail: bool = False
    ):
        self.model_name = model_name
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output
        self.simulated_latency_ms = simulated_latency_ms
        self.should_fail = should_fail

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        start_time = time.time()

        if self.should_fail:
            raise RuntimeError(f"MockProviderError: 503 Provider `{self.model_name}` temporarily unavailable")

        # Simulate latency
        if self.simulated_latency_ms > 0:
            time.sleep(self.simulated_latency_ms / 1000.0)

        # Analyze message history to determine next step in reasoning loop
        all_text = " ".join([m.get("content", "") or "" for m in messages])
        last_message = messages[-1] if messages else {}
        last_role = last_message.get("role")
        last_content = last_message.get("content", "")

        tool_calls: List[ToolCallRequest] = []
        content = None

        # Check if the last turn was a tool response
        executed_tool_names = [
            m.get("tool_name") or m.get("name")
            for m in messages
            if m.get("role") in ["tool", "function"]
        ]

        # Case 1: Standard Disputed Charge Remediation (TK-4401 / INV-8802 / $189.50)
        if "TK-4401" in all_text or "INV-8802" in all_text or "189.50" in all_text or "unrecognized charge" in all_text.lower():
            if "get_crm_ticket" not in executed_tool_names and "get_invoice_by_id" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="get_crm_ticket",
                    arguments={"ticket_id": "TK-4401"}
                ))
                content = "I will inspect support ticket TK-4401 to understand the customer dispute."
            elif "get_invoice_by_id" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="get_invoice_by_id",
                    arguments={"invoice_id": "INV-8802"}
                ))
                content = "Ticket TK-4401 references invoice INV-8802 for $189.50. I will verify the invoice in the relational database."
            elif "find_charge_by_order" not in executed_tool_names and "get_charge_details" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="find_charge_by_order",
                    arguments={"order_id": "ORD-7702"}
                ))
                content = "Invoice INV-8802 corresponds to order ORD-7702. Fetching payment gateway charge details."
            elif "issue_refund" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="issue_refund",
                    arguments={
                        "charge_id": "ch_7702",
                        "amount": 189.50,
                        "reason": "customer_dispute_unrecognized_charge",
                        "idempotency_key": "idemp_ref_tk4401_01"
                    }
                ))
                content = "Charge ch_7702 is disputed and captured for $189.50. Issuing an idempotent refund."
            elif "update_crm_ticket" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="update_crm_ticket",
                    arguments={"ticket_id": "TK-4401", "new_status": "RESOLVED"}
                ))
                content = "Refund successfully executed. Updating CRM ticket TK-4401 to RESOLVED."
            else:
                content = (
                    "Successfully resolved the billing dispute for Acme Global Corp (ticket TK-4401). "
                    "Verified invoice INV-8802 ($189.50) and linked charge ch_7702. "
                    "Issued a full refund of $189.50 and marked support ticket TK-4401 as RESOLVED."
                )

        # Case 2: High-Value Refund Scenario ($1450.00 - Tests HITL Trigger)
        elif "1450" in all_text or "INV-8801" in all_text or "ORD-7701" in all_text:
            if "get_invoice_by_id" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="get_invoice_by_id",
                    arguments={"invoice_id": "INV-8801"}
                ))
                content = "Querying invoice INV-8801 to inspect order linkage and amount."
            elif "find_charge_by_order" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="find_charge_by_order",
                    arguments={"order_id": "ORD-7701"}
                ))
                content = "Looking up gateway charge for order ORD-7701."
            elif "issue_refund" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="issue_refund",
                    arguments={
                        "charge_id": "ch_7701",
                        "amount": 1450.00,
                        "reason": "contract_cancellation",
                        "idempotency_key": "idemp_ref_ord7701_01"
                    }
                ))
                content = "Attempting to issue refund of $1450.00 on charge ch_7701. Note: This exceeds auto-approval limits and triggers HITL gate."
            else:
                content = (
                    "High-value refund of $1450.00 on charge ch_7701 has been processed following authorization. "
                    "Enterprise customer Acme Global Corp account has been credited."
                )

        # Case 3: Infrastructure / DLQ Incident
        elif "dlq" in all_text.lower() or "dead letter" in all_text.lower() or "webhook" in all_text.lower():
            if "get_dlq_messages" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="get_dlq_messages",
                    arguments={"status_filter": "DEAD"}
                ))
                content = "Inspecting Dead Letter Queue for dropped events."
            elif "replay_dlq_message" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="replay_dlq_message",
                    arguments={"message_id": "dlq_msg_101"}
                ))
                content = "Replaying dropped billing dispute webhook dlq_msg_101."
            else:
                content = "DLQ message dlq_msg_101 was successfully replayed back to the event bus. Infrastructure health restored."

        # Case 4: Ambiguous Request (No specific customer or ID provided)
        elif "refund" in all_text.lower() and not re.search(r"\b(CUST-\d+|INV-\d+|ORD-\d+|TK-\d+|\$\d+)\b", all_text):
            content = (
                "CLARIFICATION_REQUIRED: The request to issue a refund is ambiguous. "
                "Please specify the customer identifier (e.g. CUST-901), invoice ID (e.g. INV-8802), "
                "or support ticket number so that I can look up the corresponding transaction safely."
            )

        # Case 5: General Default / Read
        else:
            if "inspect_system_health" not in executed_tool_names:
                tool_calls.append(ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:6]}",
                    name="inspect_system_health",
                    arguments={}
                ))
                content = "Inspecting overall enterprise system health."
            else:
                content = "Enterprise system health inspection completed. All database and payment services operational."

        latency_ms = round((time.time() - start_time) * 1000, 2)
        prompt_tokens = len(all_text.split()) * 2 + 50
        completion_tokens = len((content or "").split()) * 2 + (len(tool_calls) * 30)

        cost_usd = (
            (prompt_tokens / 1000.0) * self.cost_per_1k_input +
            (completion_tokens / 1000.0) * self.cost_per_1k_output
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=self.model_name,
            latency_ms=latency_ms,
            estimated_cost_usd=cost_usd
        )
