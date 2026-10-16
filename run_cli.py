"""
NexusOps CLI: Command Line Operations & Benchmark Harness.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nexusops.agent.runner import AgentRunner
from nexusops.evals.benchmarks import BENCHMARK_SUITE
from nexusops.evals.harness import EvaluationHarness
from nexusops.integrations.crm_service import CRMService
from nexusops.integrations.database import DatabaseService
from nexusops.integrations.infrastructure import InfrastructureService
from nexusops.integrations.payment_gateway import PaymentGatewayService
from nexusops.routing.router import ModelRouter
from nexusops.safety.compensation import CompensationLedger
from nexusops.safety.hitl import HITLGatekeeper
from nexusops.safety.idempotency import IdempotencyEngine
from nexusops.tools.registry import ToolRegistry

console = Console()


def create_services():
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
    return runner, hitl, compensation


async def cmd_run_task(prompt: str):
    console.print(Panel(f"[bold cyan]Task Prompt:[/bold cyan] {prompt}", title="NexusOps Mission Control"))
    runner, hitl, compensation = create_services()

    state = await runner.execute_task(prompt)

    # Print Plan
    if state.plan_steps:
        table_plan = Table(title="Execution Milestones", show_header=True)
        table_plan.add_column("Step", style="cyan")
        table_plan.add_column("Milestone Description")
        for idx, step in enumerate(state.plan_steps):
            table_plan.add_row(str(idx + 1), step)
        console.print(table_plan)

    # Print Tool Calls
    if state.tool_observations:
        table_tools = Table(title="Tool Observations", show_header=True)
        table_tools.add_column("#", style="magenta")
        table_tools.add_column("Tool")
        table_tools.add_column("Arguments")
        table_tools.add_column("Result")
        for idx, obs in enumerate(state.tool_observations):
            table_tools.add_row(str(idx + 1), obs["tool"], str(obs["arguments"]), str(obs["result"]))
        console.print(table_tools)

    # HITL Challenge if paused
    if state.pending_challenge:
        console.print(Panel(
            f"[bold red]HITL Challenge Triggered![/bold red]\n"
            f"Action: {state.pending_challenge.tool_name}\n"
            f"Args: {state.pending_challenge.arguments}\n"
            f"Reason: {state.pending_challenge.reason}\n"
            f"Challenge Token: [bold yellow]{state.pending_challenge.challenge_token}[/bold yellow]",
            title="Human-In-The-Loop Security Gate",
            border_style="red"
        ))

    # Print Result
    status_color = "green" if state.status.value == "COMPLETED" else "yellow"
    console.print(Panel(
        f"[bold]Status:[/bold] [{status_color}]{state.status.value}[/{status_color}]\n"
        f"[bold]Resolution:[/bold] {state.final_response}",
        title="Agent Execution Summary",
        border_style=status_color
    ))

    # Print Telemetry
    if state.tracer:
        summary = state.tracer.get_summary()
        console.print(
            f"[dim]Duration: {summary['total_duration_ms']}ms | "
            f"Tokens: {summary['tokens']['total']} (Prompt: {summary['tokens']['prompt']}, Comp: {summary['tokens']['completion']}) | "
            f"Cost: ${summary['estimated_cost_usd']:.6f}[/dim]\n"
        )


async def cmd_evals():
    console.print(Panel("[bold green]Executing NexusOps Benchmark Suite...[/bold green]", title="Evaluation Harness"))
    harness = EvaluationHarness()
    summary = await harness.run_benchmark()

    table = Table(title="Continuous Evaluation Scorecard", show_header=True)
    table.add_column("Scenario ID", style="cyan")
    table.add_column("Title")
    table.add_column("Status Match")
    table.add_column("Tool Prec.")
    table.add_column("Tool Rec.")
    table.add_column("Grounding")
    table.add_column("Safety")
    table.add_column("Latency")
    table.add_column("Verdict", style="bold")

    for r in summary["results"]:
        verdict = "[green]PASSED[/green]" if r["passed"] else "[red]FAILED[/red]"
        table.add_row(
            r["scenario_id"],
            r["title"][:30],
            "✓" if r["status_match"] else "✕",
            f"{r['tool_precision'] * 100:.0f}%",
            f"{r['tool_recall'] * 100:.0f}%",
            f"{r['grounding_score'] * 100:.0f}%",
            "✓" if r["safety_compliant"] else "✕",
            f"{r['latency_ms']:.1f}ms",
            verdict
        )
    console.print(table)

    console.print(Panel(
        f"[bold]Pass Rate:[/bold] [green]{summary['pass_rate_pct']}%[/green] ({summary['passed_scenarios']}/{summary['total_scenarios']})\n"
        f"[bold]Avg Grounding Score:[/bold] {summary['avg_grounding_score'] * 100:.1f}%\n"
        f"[bold]Avg Latency:[/bold] {summary['avg_latency_ms']}ms | [bold]Total Cost:[/bold] ${summary['total_cost_usd']:.6f}",
        title="Aggregate Scorecard Summary",
        border_style="cyan"
    ))


def cmd_serve(port: int = 8000):
    import uvicorn
    console.print(f"[bold green]Starting NexusOps Web Mission Control at http://127.0.0.1:{port}[/bold green]")
    uvicorn.run("nexusops.web.app:app", host="127.0.0.1", port=port, reload=False)


def main():
    parser = argparse.ArgumentParser(description="NexusOps AI Operational Engine CLI")
    subparsers = parser.add_subparsers(dest="command")

    # task
    task_parser = subparsers.add_parser("task", help="Execute an operational task")
    task_parser.add_argument("prompt", type=str, help="Instruction for the agent")

    # evals
    subparsers.add_parser("evals", help="Run the continuous evaluation benchmark suite")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Launch interactive web dashboard")
    serve_parser.add_argument("--port", type=int, default=8000, help="Web server port")

    args = parser.parse_args()

    if args.command == "task":
        asyncio.run(cmd_run_task(args.prompt))
    elif args.command == "evals":
        asyncio.run(cmd_evals())
    elif args.command == "serve":
        cmd_serve(args.port)
    else:
        # Default run demo task
        demo_prompt = "Investigate urgent ticket TK-4401 regarding unrecognized charge for invoice INV-8802 ($189.50) and remediate."
        asyncio.run(cmd_run_task(demo_prompt))


if __name__ == "__main__":
    main()
