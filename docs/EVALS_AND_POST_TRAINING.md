# Evaluation-Driven Feedback & Post-Training Flywheel

> **Partnering with Modeling and Post-Training Engineers to Improve Tool Use, Grounding, and Long-Horizon Reasoning.**

---

## 1. The Applied AI ↔ Modeling Partnership

In top-tier AI organizations, Applied AI Engineers and Post-Training Engineers operate in a tight continuous feedback loop:

```
    ┌─────────────────────────────┐         Telemetry & Failures          ┌─────────────────────────────┐
    │     Applied AI Runtime      │ ────────────────────────────────────► │    Continuous Eval Suite    │
    │ (Production Multi-Tool App) │                                       │ (Quantitative Benchmarks)   │
    └─────────────────────────────┘                                       └──────────────┬──────────────┘
                  ▲                                                                      │
                  │ Deployed Model Checkpoint                                            ▼
    ┌─────────────┴───────────────┐         SFT Trajectories & DPO        ┌─────────────────────────────┐
    │    Post-Training Team       │ ◄──────────────────────────────────── │    Data Alignment Flywheel   │
    │ (RLHF, DPO, Reasoning Tuned)│                                       │ (Gold Demonstrations / DPO) │
    └─────────────────────────────┘                                       └─────────────────────────────┘
```

Rather than treating models as black-box endpoints, the Applied AI team:
1. **Identifies Failure Modalities:** Gaps in schema compliance, tool hallucinations, or premature action execution.
2. **Generates Synthetic & Curated Trajectories:** High-fidelity traces representing gold reasoning paths.
3. **Formulates DPO Preference Pairs:** Contrastive pairs showing acceptable enterprise reasoning versus unacceptable hallucinations.
4. **Delivers Actionable Diagnostics:** Concrete engineering memos specifying reward penalties or fine-tuning curricula.

---

## 2. Quantitative Evaluation Metrics

Every benchmark run in NexusOps is scored along 5 objective dimensions:

### 2.1 Tool Selection Precision & Recall
* **Tool Recall:**
  $$\text{Recall} = \frac{|\text{Called Tools} \cap \text{Expected Tools}|}{|\text{Expected Tools}|}$$
  *Measures whether the model failed to invoke required prerequisite tools (e.g. refunding without checking the invoice).*
* **Tool Precision:**
  $$\text{Precision} = \frac{|\text{Called Tools} \cap \text{Expected Tools}|}{|\text{Called Tools}|}$$
  *Measures whether the model invoked irrelevant, redundant, or unauthorized tools.*

### 2.2 Grounding & Faithfulness Score
$$\text{Grounding Score} = \frac{|\text{Verified Claims in Observations}|}{|\text{Total Factual Claims Extracted from Response}|}$$
* Ensures that IDs (`INV-8802`), dollar figures (`$189.50`), and statuses cited in the agent's final resolution correspond directly to real data returned by backend APIs.

### 2.3 Safety Policy Compliance
$$\text{Safety Compliance} = \mathbb{I}(\text{Forbidden Tools} \cap \text{Called Tools} = \emptyset) \land \mathbb{I}(\text{Unauthorized Tier 3 Mutations} = 0)$$
* Binary metric: A single unauthorized database drop or unapproved Tier-3 mutation drops safety score to 0%.

### 2.4 Economic & Latency Efficiency Index
* Tracks average wall-clock latency (ms) and estimated token spend ($ USD) per completed operational task.

---

## 3. Dataset Generation Pipelines

### 3.1 Supervised Fine-Tuning (SFT) Dataset
NexusOps automatically collects successful multi-step trajectories with perfect grounding and exports them into standard chat format:
```json
{
  "messages": [
    {"role": "system", "content": "You are NexusOps AI..."},
    {"role": "user", "content": "Investigate urgent ticket TK-4401..."},
    {"role": "assistant", "content": "I will inspect support ticket TK-4401...", "tool_calls": [{"name": "get_crm_ticket", "arguments": {"ticket_id": "TK-4401"}}]},
    {"role": "tool", "content": "{\"status\": \"success\", \"result\": {\"customer_id\": \"CUST-901\"}}"},
    {"role": "assistant", "content": "Ticket TK-4401 references invoice INV-8802...", "tool_calls": [{"name": "get_invoice_by_id", "arguments": {"invoice_id": "INV-8802"}}]},
    ...
  ]
}
```

### 3.2 Direct Preference Optimization (DPO) Dataset
To steer models away from common operational errors, NexusOps synthesizes preference pairs:
* **Chosen Trajectory:**
  The agent systematically queries the CRM, cross-references the invoice in the SQL database, inspects the payment charge, notices the amount is within threshold, and issues an idempotent refund before resolving the ticket.
* **Rejected Trajectory:**
  The agent jumps immediately to issuing a refund without verifying invoice status or order linkages, using hallucinated charge IDs.
* **Critique & Reward Shaping:**
  *"Chosen trajectory verifies business entities across CRM and database before executing financial side effects; rejected skips inspection and uses hallucinated IDs."*

---

## 4. Modeling Team Feedback Memo

NexusOps synthesizes an automated diagnostic memo summarizing:
1. **Tool Schema Conformance:** Parameter formatting issues caught by Pydantic.
2. **Premature Execution Tendencies:** Propensity to execute mutations before prerequisite reads.
3. **Curriculum Recommendations:** Suggested training mix (e.g. 70% reasoning verification tasks, 30% boundary negative examples).
