"""
NexusOps Enterprise Agent Execution Runtime.

Orchestrates the complete ReAct + Reflection lifecycle:
- Input guardrail sanitization & injection defense
- Intent disambiguation
- Model routing with circuit breakers & caching
- Tool execution with idempotency & cryptographic HITL gating
- SAGA compensation rollbacks on failure
- Output grounding verification & telemetry reporting
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from nexusops.agent.disambiguation import DisambiguationEngine
from nexusops.agent.planner import ExecutionPlanner
from nexusops.agent.state import AgentState, AgentStatus
from nexusops.routing.router import ModelRouter, RoutingPolicy
from nexusops.safety.compensation import CompensationLedger
from nexusops.safety.guardrails import GroundingVerifier, PIIRedactor, PromptInjectionGuard
from nexusops.safety.hitl import HITLGatekeeper, RiskTier
from nexusops.telemetry.tracer import SpanKind, Tracer
from nexusops.tools.registry import ToolRegistry


class AgentRunner:
    """Runtime engine for executing enterprise agent tasks."""

    def __init__(
        self,
        router: ModelRouter,
        registry: ToolRegistry,
        hitl: HITLGatekeeper,
        compensation: CompensationLedger,
        max_turns: int = 10,
    ):
        self.router = router
        self.registry = registry
        self.hitl = hitl
        self.compensation = compensation
        self.max_turns = max_turns
        self._active_sessions: Dict[str, AgentState] = {}

    def get_session(self, session_id: str) -> Optional[AgentState]:
        return self._active_sessions.get(session_id)

    async def execute_task(
        self,
        task_prompt: str,
        session_id: Optional[str] = None,
        bypass_hitl_token: Optional[str] = None
    ) -> AgentState:
        """Executes an agent task end-to-end under full production safety guarantees."""
        # 1. Initialize State and Tracer
        tracer = Tracer()
        span_root = tracer.start_span("agent_execution", kind=SpanKind.AGENT, attributes={"prompt": task_prompt})

        state = AgentState(
            session_id=session_id or f"sess_{int(time.time() * 1000) % 1000000}",
            task_prompt=task_prompt,
            tracer=tracer
        )
        self._active_sessions[state.session_id] = state

        # 2. Input Guardrails: Prompt Injection Check
        guard_span = tracer.start_span("input_guardrails", kind=SpanKind.SAFETY_GUARD)
        injection_result = PromptInjectionGuard.evaluate(task_prompt)
        if not injection_result.is_safe:
            tracer.end_span(guard_span, status="ERROR", error="Prompt injection detected")
            tracer.end_span(span_root, status="ERROR", error="Security policy violation")
            state.status = AgentStatus.FAILED
            state.error = f"Security Policy Violation: Malicious input patterns detected: {injection_result.flags}"
            state.final_response = "Execution rejected due to security guardrail violation."
            state.completed_at = time.time()
            return state
        tracer.end_span(guard_span, status="OK")

        # 3. Disambiguation Check
        disambig = DisambiguationEngine.analyze(task_prompt)
        if disambig.is_ambiguous:
            state.status = AgentStatus.CLARIFICATION_REQUIRED
            state.final_response = disambig.clarification_question
            state.metadata = {"suggested_options": disambig.suggested_options}
            tracer.end_span(span_root, status="OK")
            state.completed_at = time.time()
            return state

        # 4. Synthesize Plan
        state.plan_steps = ExecutionPlanner.create_plan(task_prompt)
        state.status = AgentStatus.EXECUTING_TOOLS

        # Initialize conversation messages
        system_instruction = (
            "You are NexusOps AI, an elite enterprise autonomous operations engineer. "
            "You remediate customer billing disputes, reconcile database ledgers, and resolve infrastructure incidents. "
            "Always inspect records before taking action. Never invent identifiers. "
            "Action Risk Policy: Read actions are Tier-1. Low-risk ticket mutations are Tier-2. "
            "Financial transactions > $200 are Tier-3 and require Human-in-the-loop authorization."
        )
        state.add_message(role="system", content=system_instruction)
        # Redact any PII from prompt before feeding to model
        safe_prompt = PIIRedactor.redact(task_prompt)
        state.add_message(role="user", content=safe_prompt)

        # 5. Autonomous ReAct Execution Loop
        turn = 0
        tool_schemas = self.registry.get_schemas_for_llm()

        while turn < self.max_turns:
            turn += 1

            # Generate model completion
            try:
                llm_resp = await self.router.route_and_generate(
                    messages=state.messages,
                    tools=tool_schemas,
                    policy=RoutingPolicy.AUTO,
                    tracer=tracer
                )
            except Exception as e:
                # LLM Failure -> Trigger SAGA Rollback
                rollback_res = await self.compensation.rollback_all(self._compensation_executor)
                state.rollback_log.extend(rollback_res)
                state.status = AgentStatus.ROLLED_BACK
                state.error = f"Model execution failed: {str(e)}. Executed compensation rollback."
                tracer.end_span(span_root, status="ERROR", error=state.error)
                state.completed_at = time.time()
                return state

            # Record model thought / message
            state.add_message(
                role="assistant",
                content=llm_resp.content,
                tool_calls=[tc.__dict__ for tc in llm_resp.tool_calls] if llm_resp.tool_calls else None
            )

            # If model produced no tool calls, it has finished reasoning
            if not llm_resp.tool_calls:
                state.final_response = llm_resp.content or "Task completed."
                break

            # Execute tool calls
            for tc in llm_resp.tool_calls:
                # Execute tool
                tool_res = await self.registry.execute_tool(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    tracer=tracer,
                    bypass_hitl_token=bypass_hitl_token
                )

                # Check if tool execution was paused for HITL approval
                if tool_res.get("status") == "APPROVAL_REQUIRED":
                    challenge = self.hitl.get_challenge(tool_res["challenge_token"])
                    state.status = AgentStatus.PAUSED_FOR_APPROVAL
                    state.pending_challenge = challenge
                    state.final_response = (
                        f"Action paused for human approval: {challenge.impact_summary} "
                        f"Reason: {challenge.reason}"
                    )
                    tracer.end_span(span_root, status="PAUSED", error="Waiting for human approval")
                    return state

                # Record observation
                state.tool_observations.append({
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "result": tool_res
                })

                # Append tool observation message to model history
                state.add_message(
                    role="tool",
                    name=tc.name,
                    tool_call_id=tc.call_id,
                    content=str(tool_res)
                )

                # Check if tool failed critically
                if tool_res.get("status") == "error":
                    # Tool failed -> Execute compensation rollback for previously executed steps
                    rollback_res = await self.compensation.rollback_all(self._compensation_executor)
                    state.rollback_log.extend(rollback_res)
                    state.status = AgentStatus.ROLLED_BACK
                    state.error = f"Tool `{tc.name}` failed: {tool_res.get('error')}. Rollback executed."
                    tracer.end_span(span_root, status="ERROR", error=state.error)
                    state.completed_at = time.time()
                    return state

        # 6. Post-Execution Grounding Verification & PII Sanitization
        verify_span = tracer.start_span("grounding_verification", kind=SpanKind.SAFETY_GUARD)
        grounding_report = GroundingVerifier.verify(
            response_text=state.final_response or "",
            tool_observations=state.tool_observations
        )
        state.grounding_report = grounding_report
        tracer.end_span(verify_span, status="OK" if grounding_report["is_grounded"] else "WARN")

        # Sanitize final response before returning to user
        state.final_response = PIIRedactor.redact(state.final_response or "")
        state.status = AgentStatus.COMPLETED
        state.completed_at = time.time()
        tracer.end_span(span_root, status="OK")

        return state

    async def resume_after_approval(self, session_id: str, challenge_token: str) -> AgentState:
        """Resumes an agent session that was paused for HITL approval."""
        state = self.get_session(session_id)
        if not state:
            raise ValueError(f"Session `{session_id}` not found")

        challenge = self.hitl.get_challenge(challenge_token)
        if not challenge or challenge.status.value != "APPROVED":
            raise ValueError("Challenge token must be approved by an authorized operator before resumption.")

        # Reset status and clear pending challenge
        state.pending_challenge = None
        state.status = AgentStatus.EXECUTING_TOOLS

        # Re-execute task with bypass token
        return await self.execute_task(
            task_prompt=state.task_prompt,
            session_id=session_id,
            bypass_hitl_token=challenge_token
        )

    async def _compensation_executor(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Internal callback used by compensation ledger during rollback."""
        return await self.registry.execute_tool(tool_name, arguments)
