"""
NexusOps Interactive Web Mission Control & API Server.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from nexusops.agent.runner import AgentRunner
from nexusops.evals.benchmarks import BENCHMARK_SUITE
from nexusops.evals.flywheel import PostTrainingFlywheel
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

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="NexusOps: Enterprise AI Incident & Financial Remediation Platform",
    version="1.0.0",
    description="Production-grade AI integration, safe system orchestration, and model post-training flywheel."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"
static_dir.mkdir(parents=True, exist_ok=True)
templates_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# Global Services State
class AppContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.db = DatabaseService(":memory:")
        self.payment = PaymentGatewayService()
        self.crm = CRMService()
        self.infra = InfrastructureService()
        self.idempotency = IdempotencyEngine()
        self.hitl = HITLGatekeeper()
        self.compensation = CompensationLedger()
        self.registry = ToolRegistry(
            db=self.db,
            payment=self.payment,
            crm=self.crm,
            infra=self.infra,
            idempotency=self.idempotency,
            hitl=self.hitl,
            compensation=self.compensation
        )
        self.router = ModelRouter()
        self.runner = AgentRunner(
            router=self.router,
            registry=self.registry,
            hitl=self.hitl,
            compensation=self.compensation
        )
        self.flywheel = PostTrainingFlywheel()
        self.harness = EvaluationHarness(flywheel=self.flywheel)

ctx = AppContext()


class RunRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None


class HITLDecisionRequest(BaseModel):
    session_id: str
    challenge_token: str
    approver: str = "security_lead"
    reason: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/health")
async def get_health():
    return {
        "status": "HEALTHY",
        "health": ctx.infra.inspect_system_health(),
        "cache": ctx.router.cache.stats(),
        "pending_challenges_count": len(ctx.hitl.list_pending_challenges()),
        "compensation_history_count": len(ctx.compensation.get_history())
    }


@app.get("/api/scenarios")
async def list_scenarios():
    return [
        {
            "id": s.id,
            "title": s.title,
            "category": s.category.value,
            "prompt": s.prompt,
            "description": s.description,
            "expected_status": s.expected_status
        }
        for s in BENCHMARK_SUITE
    ]


@app.post("/api/run")
async def run_task(req: RunRequest):
    state = await ctx.runner.execute_task(req.prompt, session_id=req.session_id)
    ctx.flywheel.record_run(state)
    return state.to_dict()


@app.post("/api/hitl/approve")
async def approve_hitl(req: HITLDecisionRequest):
    ok, msg = ctx.hitl.approve(req.challenge_token, approver=req.approver)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Resume the agent session
    state = await ctx.runner.resume_after_approval(req.session_id, req.challenge_token)
    ctx.flywheel.record_run(state)
    return {
        "status": "APPROVED_AND_RESUMED",
        "message": msg,
        "state": state.to_dict()
    }


@app.post("/api/hitl/reject")
async def reject_hitl(req: HITLDecisionRequest):
    ok, msg = ctx.hitl.reject(req.challenge_token, reason=req.reason or "Rejected by reviewer", approver=req.approver)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "REJECTED", "message": msg}


@app.get("/api/evals")
async def run_evals():
    summary = await ctx.harness.run_benchmark()
    return summary


@app.get("/api/flywheel/sft")
async def get_sft_dataset():
    return ctx.flywheel.export_sft_dataset()


@app.get("/api/flywheel/dpo")
async def get_dpo_dataset():
    return ctx.flywheel.generate_dpo_pairs()


@app.get("/api/flywheel/memo")
async def get_modeling_memo():
    summary = await ctx.harness.run_benchmark()
    return summary.get("modeling_memo", {})


@app.post("/api/reset")
async def reset_environment():
    ctx.reset()
    return {"status": "ENVIRONMENT_RESET_SUCCESS"}
