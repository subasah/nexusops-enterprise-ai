"""
NexusOps Evaluation Harness & Benchmark Suite Runner.

Executes test scenarios against the agent runner with fresh state isolation,
calculates aggregate scorecards, and feeds results to the post-training flywheel.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from nexusops.agent.runner import AgentRunner
from nexusops.evals.benchmarks import BENCHMARK_SUITE, BenchmarkScenario
from nexusops.evals.flywheel import PostTrainingFlywheel
from nexusops.evals.metrics import MetricsEvaluator, ScenarioEvaluationResult
from nexusops.integrations.crm_service import CRMService
from nexusops.integrations.database import DatabaseService
from nexusops.integrations.infrastructure import InfrastructureService
from nexusops.integrations.payment_gateway import PaymentGatewayService
from nexusops.routing.router import ModelRouter
from nexusops.safety.compensation import CompensationLedger
from nexusops.safety.hitl import HITLGatekeeper
from nexusops.safety.idempotency import IdempotencyEngine
from nexusops.tools.registry import ToolRegistry


class EvaluationHarness:
    """Automated benchmarking harness for agent reliability, safety, and grounding."""

    def __init__(self, flywheel: Optional[PostTrainingFlywheel] = None):
        self.flywheel = flywheel or PostTrainingFlywheel()

    def _build_fresh_environment(self) -> tuple[AgentRunner, DatabaseService, PaymentGatewayService, CRMService, InfrastructureService]:
        """Creates a completely isolated environment with seeded enterprise state."""
        db = DatabaseService(":memory:")
        payment = PaymentGatewayService()
        crm = CRMService()
        infra = InfrastructureService()

        idempotency = IdempotencyEngine()
        hitl = HITLGatekeeper()
        compensation = CompensationLedger()

        registry = ToolRegistry(
            db=db,
            payment=payment,
            crm=crm,
            infra=infra,
            idempotency=idempotency,
            hitl=hitl,
            compensation=compensation
        )

        router = ModelRouter()
        runner = AgentRunner(
            router=router,
            registry=registry,
            hitl=hitl,
            compensation=compensation
        )
        return runner, db, payment, crm, infra

    async def run_benchmark(self, scenario_id: Optional[str] = None) -> Dict[str, Any]:
        """Runs one or all benchmarks and compiles aggregate metrics."""
        scenarios = (
            [s for s in BENCHMARK_SUITE if s.id == scenario_id]
            if scenario_id
            else BENCHMARK_SUITE
        )

        start_time = time.time()
        results: List[ScenarioEvaluationResult] = []

        for sc in scenarios:
            runner, db, payment, crm, infra = self._build_fresh_environment()
            state = await runner.execute_task(sc.prompt)
            eval_res = MetricsEvaluator.evaluate(sc, state)
            results.append(eval_res)
            self.flywheel.record_run(state, eval_res)

        total_scenarios = len(results)
        passed_scenarios = len([r for r in results if r.passed])
        pass_rate = (passed_scenarios / total_scenarios * 100) if total_scenarios > 0 else 0.0

        avg_precision = sum(r.tool_precision for r in results) / total_scenarios if total_scenarios else 0.0
        avg_recall = sum(r.tool_recall for r in results) / total_scenarios if total_scenarios else 0.0
        avg_grounding = sum(r.grounding_score for r in results) / total_scenarios if total_scenarios else 0.0
        avg_latency = sum(r.latency_ms for r in results) / total_scenarios if total_scenarios else 0.0
        total_tokens = sum(r.total_tokens for r in results)
        total_cost = sum(r.cost_usd for r in results)

        summary = {
            "total_scenarios": total_scenarios,
            "passed_scenarios": passed_scenarios,
            "pass_rate_pct": round(pass_rate, 1),
            "avg_tool_precision": round(avg_precision, 2),
            "avg_tool_recall": round(avg_recall, 2),
            "avg_grounding_score": round(avg_grounding, 2),
            "avg_latency_ms": round(avg_latency, 1),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "execution_duration_sec": round(time.time() - start_time, 2),
            "results": [r.to_dict() for r in results],
        }

        # Generate memo for modeling team
        memo = self.flywheel.generate_modeling_team_memo(summary)
        summary["modeling_memo"] = memo

        return summary
