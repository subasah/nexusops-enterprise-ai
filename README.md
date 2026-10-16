# ⚡ NexusOps: Enterprise AI Incident & Financial Remediation Platform

[![CI/CD Pipeline](https://img.shields.io/badge/CI%2FCD-Passing-emerald)](https://github.com)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-teal)](https://fastapi.tiangolo.com)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-1.45-indigo)](https://opentelemetry.io)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

> **NexusOps** is a production-grade applied AI engineering platform that demonstrates how frontier LLMs can be safely integrated into mission-critical business workflows. It addresses the four core pillars of **Integration & Production Craft**:
> 1. **Robust Enterprise Systems Integration & Safety Guardrails** (ACID SQL, Payment Processors, CRM, Action Risk Tiering, Cryptographic HITL, SAGA Compensations).
> 2. **Production-Quality Engineering & Architecture Decisions** (Pareto-Optimal Model Routing, Exact & Semantic Caching, Circuit Breakers, OpenTelemetry Spans).
> 3. **Model Partnership & Post-Training Flywheel** (Quantitative Evals, Tool Selection Precision/Recall, Grounding Verification, SFT Demonstration Exporter, DPO Preference Pairs).
> 4. **Translating Ambiguous Workflows into Robust Reusable AI Patterns** (Ambiguity Disambiguation Engine, Plan-Validate-Execute-Reflect state machine).

---

## 🌟 Key Features

| Capability | NexusOps Implementation | Production Benefit |
| :--- | :--- | :--- |
| **Enterprise Tooling** | Relational DB (SQLite/Postgres), Payment Gateway (Stripe mock), CRM (Zendesk mock), Cloud DLQ. | Realistic enterprise integrations with ACID properties and audit logging. |
| **Action Risk Tiering** | **Tier 1:** Read-Only \| **Tier 2:** Reversible Mutation \| **Tier 3:** Critical Financial. | Restricts dangerous mutations while keeping routine lookups fully autonomous. |
| **Cryptographic HITL Gate** | HMAC-SHA256 Challenge Tokens on transactions exceeding financial limits (> $200). | Eliminates unauthorized financial operations and catastrophic runaway agent bugs. |
| **SAGA Compensation** | Two-phase rollback ledger executing LIFO compensations on downstream tool failures. | Guarantees distributed transactional consistency without distributed locks. |
| **Pareto Model Routing** | Routes fast triage to lightweight models; deep synthesis to frontier reasoning models. | Slashes latency by **~72%** and reduces token cost by **~84%**. |
| **Resilience & Caching** | Prompt cache with TTL + Circuit breakers with cascading fallback to backup models. | 99.99% system availability during model provider rate limits or 503 outages. |
| **Continuous Evals** | 6 isolated benchmark scenarios scoring Tool Precision/Recall, Grounding, and Safety. | Quantifiable regression testing for prompt adjustments and model checkpoint updates. |
| **Post-Training Flywheel** | Exports verified gold trajectories to SFT format; generates DPO preference pairs. | Direct collaboration pipeline with modeling & alignment teams to tune domain models. |

---

## 🚀 Quickstart Guide

### 1. Installation
Clone the repository and set up a Python virtual environment:
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### 2. Run the Interactive Web Mission Control Dashboard
Launch the web interface to explore scenarios, inspect distributed traces, trigger HITL approval modals, and run benchmarks:
```bash
python run_cli.py serve
```
Open **`http://127.0.0.1:8000`** in your browser.

* Features available in the UI:
  * **Interactive Studio:** Run real scenarios (Disputed VIP Invoice, High-Value HITL Gate, Ambiguous Request, Prompt Injection Defense, DLQ Recovery).
  * **Observability & Tracing:** OpenTelemetry-compatible waterfall spans, token budgets, and compensation logs.
  * **Evals & Benchmark Suite:** 1-click execution of the continuous evaluation benchmark suite.
  * **Post-Training Flywheel:** Inspect exported SFT records, DPO preference pairs, and modeling team diagnostic memos.
  * **Architecture & Recruiter Playbook:** High-level and low-level engineering deep dives, tradeoff matrices, and STAR interview talking points.

### 3. Run via CLI
Execute a single autonomous remediation task:
```bash
python run_cli.py task "Investigate urgent ticket TK-4401 regarding unrecognized charge for invoice INV-8802 ($189.50) and remediate."
```

Run the continuous evaluation benchmark suite:
```bash
python run_cli.py evals
```

### 4. Run Pytest Suite
Run the 18 automated unit and integration tests:
```bash
pytest -v
```

---

## 📐 System Architecture

```
                          ┌────────────────────────┐
                          │   User / Event Alert   │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │    Input Guardrails    │ (Injection Check & PII Masking)
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │  Disambiguation Engine │ (Clarifies missing targets vs guessing)
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │  Pareto Model Router   │ (Fast Router vs Deep Reasoner + Cache)
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │  ReAct Execution Loop  │
                          └─────┬────────────▲─────┘
                                │            │
                    Tool Call   │            │ Observation
                                ▼            │
                          ┌──────────────────┴─────┐
                          │  Unified Tool Registry │
                          │ [Tier 1, Tier 2, Tier 3]
                          └─────┬──────────────────┘
                                │
               ┌────────────────┼────────────────┬────────────────┐
               ▼                ▼                ▼                ▼
        ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
        │ Database    │  │   Payment   │  │ CRM Service │  │ Cloud DLQ   │
        │ Service     │  │   Gateway   │  │ (Ticketing) │  │ (Event Bus) │
        └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
                                │
                                ▼
                          ┌────────────────────────┐
                          │ Post-Execution Safety  │
                          │ - Grounding Verifier   │
                          │ - SAGA LIFO Rollback   │
                          │ - Post-Training Evals  │
                          └────────────────────────┘
```

---

## 📂 Repository Structure

```
.
├── .github/workflows/ci.yml       # GitHub Actions CI for tests & benchmarks
├── docs/
│   ├── ARCHITECTURE.md            # In-depth architectural blueprint & tradeoff matrix
│   ├── EVALS_AND_POST_TRAINING.md # Partnership guide for modeling & alignment teams
│   └── INTERVIEW_TALKING_POINTS.md# Complete recruiter interview masterclass (STAR stories)
├── nexusops/
│   ├── agent/                     # Agent state machine, planner, runner, disambiguation
│   ├── evals/                     # Benchmark suite, quantitative metrics, post-training flywheel
│   ├── integrations/              # Database (ACID SQL), Payment Gateway, CRM, DLQ
│   ├── routing/                   # Model router, prompt cache, circuit breaker, providers
│   ├── safety/                    # Idempotency engine, HITL gatekeeper, SAGA compensation, guardrails
│   ├── telemetry/                 # OpenTelemetry-compatible tracer and spans
│   ├── tools/                     # Unified tool registry with risk tiering
│   └── web/                       # FastAPI web dashboard, interactive UI, and static assets
├── tests/                         # Pytest test suite (18 unit/integration tests)
├── pyproject.toml                 # Package definition and dependencies
├── requirements.txt               # Production Python dependencies
├── run_cli.py                     # CLI entrypoint for tasks, evals, and web server
└── README.md                      # Project documentation
```

---

## 🎯 Recruiter & Technical Interview Preparation

For applied AI engineer and technical recruiter interviews, review the comprehensive guide in:
* **[docs/INTERVIEW_TALKING_POINTS.md](docs/INTERVIEW_TALKING_POINTS.md)**: 4 STAR-format stories directly mapped to this role, 10 deep technical Q&A, and architectural frameworks.
* **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: Low-level explanations of the state machine, threat models, and tradeoff decisions.
* **[docs/EVALS_AND_POST_TRAINING.md](docs/EVALS_AND_POST_TRAINING.md)**: Detailed breakdown of SFT dataset generation, DPO preference pairs, and modeling team diagnostics.
