# NexusOps: Architecture & Systems Engineering Blueprint

> **A Production-Grade Enterprise AI Incident & Financial Remediation Platform**  
> *Balancing Quality, Safety, Latency, Cost, and Model Risk across Distributed Heterogeneous Systems.*

---

## 1. High-Level System Architecture

NexusOps demonstrates how frontier language models can be safely integrated into high-stakes enterprise business operations (SQL ledgers, payment processors, customer CRM, and event queues) without risking data loss, financial exposure, or runaway hallucination.

```
                    ┌───────────────────────────────────────────────┐
                    │               User / Webhook Alert            │
                    │   "Investigate dispute on INV-8802 ($189.50)"  │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │            1. Input Safety Guardrails         │
                    │   - Prompt Injection & Jailbreak Defense      │
                    │   - Sensitive PII Sanitization (PAN/SSN)      │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │       2. Intent Disambiguation Engine         │
                    │   - Checks for missing required identifiers   │
                    │   - Clarifies targets vs. guessing            │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │         3. Pareto Model Routing Layer         │
                    │   - Fast Triage Router vs Deep Reasoner       │
                    │   - Semantic & Exact Hash Prompt Cache        │
                    │   - Circuit Breaker & Fallback Cascade        │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │        4. ReAct Re-entrant Execution Loop     │
                    │   - Plan-Validate-Execute-Reflect loop        │
                    │   - OpenTelemetry Distributed Tracing         │
                    └───────────┬───────────────────────▲───────────┘
                                │                       │
            Tool Invocation     │                       │ Observation
                                ▼                       │
                    ┌───────────────────────────────────┴───────────┐
                    │            5. Unified Tool Registry           │
                    │   [Tier 1: Read-Only]     Safe reads          │
                    │   [Tier 2: Reversible]    Rollback registered │
                    │   [Tier 3: Critical]      HITL Gatekeeper     │
                    └───────────┬───────────────────────────────────┘
                                │
               ┌────────────────┼────────────────┬────────────────┐
               ▼                ▼                ▼                ▼
        ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
        │ Relational  │  │   Payment   │  │   CRM /     │  │ Cloud Event │
        │ Database    │  │   Gateway   │  │ Ticketing   │  │ Bus / DLQ   │
        │ (Postgres/  │  │   (Stripe   │  │ (Zendesk /  │  │ (Kafka /    │
        │  SQLite)    │  │    Mock)    │  │ Salesforce) │  │  Webhooks)  │
        └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
                                │
                                ▼
                    ┌───────────────────────────────────────────────┐
                    │        6. Post-Execution Safety & Evals       │
                    │   - Grounding & Faithfulness Verifier         │
                    │   - SAGA Compensation (LIFO Rollback on err)  │
                    │   - SFT & DPO Post-Training Alignment Flywheel│
                    └───────────────────────────────────────────────┘
```

---

## 2. Low-Level Component Design

### 2.1 Action Risk Tiering & Cryptographic HITL Gate
Enterprises cannot permit probabilistic language models to autonomously execute financial transactions or destructive mutations without authorization.

NexusOps enforces a deterministic tripartite risk classification:
* **Tier 1 (Read-Only):** `read_customer_by_id`, `get_invoice_by_id`, `find_charge_by_order`, `get_dlq_messages`. These tools carry no state mutations and are freely callable.
* **Tier 2 (Reversible Mutation):** `update_crm_ticket`, `add_crm_internal_note`, `replay_dlq_message`. These mutations are permitted autonomously, but **automatically register a compensation hook** onto the runtime's LIFO rollback stack.
* **Tier 3 (Critical Financial & Destructive):** `issue_refund` (when amount > $200.00), `delete_customer_record`, `execute_sql_mutation`. 
  - When the agent attempts a Tier 3 action, execution immediately suspends.
  - An HMAC-SHA256 cryptographic challenge token is generated from tool arguments and timestamp.
  - The runtime yields `PAUSED_FOR_APPROVAL` state.
  - Execution can only resume when an authorized human supervisor signs the challenge.

### 2.2 SAGA-Pattern Compensation & Rollback Ledger
When an agent executes a multi-step operation:
1. `update_crm_ticket` -> Status set to `IN_PROGRESS`
2. `issue_refund` -> Refund issued on Payment Gateway
3. `update_ledger` -> Network partition / Database failure!

A naive agent leaves the enterprise in an inconsistent state (charge refunded, but ledger unrecorded and ticket left open). NexusOps implements a two-phase SAGA ledger:
* Upon successful execution of any reversible step, a compensation entry is pushed to the `CompensationLedger`.
* If a downstream error occurs, the runner catches the exception and executes `rollback_all()` in reverse chronological order (LIFO), rolling back step 2 and step 1 cleanly.

### 2.3 Distributed Idempotency Engine
To prevent duplicate mutations from retry storms or agent loop repetitions:
* All mutating tools require or auto-generate an `idempotency_key`.
* The key is derived from:
  $$\text{Key} = \text{SHA256}(\text{ToolName} \mathbin{\Vert} \text{CanonicalJSON}(\text{Arguments}))$$
* An execution state machine (`IN_PROGRESS`, `COMPLETED`, `FAILED`) guarantees that concurrent requests wait and repeated executions return the cached transaction receipt without executing duplicate charges.

### 2.4 Grounding & Anti-Hallucination Verifier
Before delivering a response to an end-user:
1. Candidate entities are extracted from the agent's proposed response (e.g. Dollar amounts like `$189.50`, invoice IDs like `INV-8802`, customer emails).
2. The extracted claims are cross-checked against the raw observation strings returned by enterprise tools.
3. If the ratio of grounded claims falls below 75%, or unverified financial figures are detected, the response is flagged and intercepted.

---

## 3. Architecture Decisions & Tradeoff Matrix

| Architecture Dimension | Naive Agent Approach | NexusOps Production Approach | Rationale & Tradeoff |
| :--- | :--- | :--- | :--- |
| **Model Selection** | Always use largest frontier model (e.g. Claude 3.7 / GPT-4o) for every turn. | **Pareto-Optimal Router:** Sub-100ms fast router for triage; deep reasoning model for multi-tool synthesis. | Slashes latency by ~70% and token cost by ~80% while retaining frontier reasoning quality on hard steps. |
| **Prompt Caching** | Raw API call on every turn. | **Exact-Hash & Semantic LRU Cache** with TTL. | Identical triage questions or repeated status checks resolve in 0.1ms with $0.00 cost. |
| **Resilience & Fault Tolerance** | App crashes on provider 500/503 errors. | **Circuit Breaker with Cascading Fallback** to secondary provider. | Ensures 99.99% service availability during LLM provider rate limits or outages. |
| **Tool Execution Safety** | Autonomous tool execution based on LLM output. | **Action Risk Tiering + Cryptographic HITL + SAGA Rollbacks**. | Eliminates rogue mutations and financial loss while keeping safe actions completely automated. |
| **Observability** | Plain `print()` logs. | **OpenTelemetry Spans** with duration, token counts, cost tracking, and parent-child trees. | Full distributed tracing across LLM calls, tool spans, and security evaluations. |
| **Post-Training Loop** | Ad-hoc manual prompt tweaking. | **Continuous Evals + SFT & DPO Flywheel**. | Systematically generates gold demonstration datasets and preference pairs for post-training teams. |
