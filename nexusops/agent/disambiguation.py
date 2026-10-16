"""
NexusOps Ambiguity Resolution & Intent Disambiguation Engine.

Detects under-specified enterprise requests (missing entity identifiers, ambiguous scopes)
and generates structured clarification prompts instead of guessing or hallucinating actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class DisambiguationResult:
    is_ambiguous: bool
    missing_fields: List[str]
    clarification_question: Optional[str] = None
    suggested_options: List[str] = None


class DisambiguationEngine:
    """Analyzes user task prompts for missing operational criteria."""

    # Patterns indicating actions that strictly require explicit targets
    DESTRUCTIVE_ACTIONS = [
        ("refund", ["customer_id", "order_id", "invoice_id", "ticket_id"]),
        ("cancel", ["order_id", "subscription_id"]),
        ("delete", ["customer_id", "entity_id"]),
    ]

    ENTITY_REGEXES = [
        re.compile(r"\bCUST-\d+\b", re.IGNORECASE),
        re.compile(r"\bORD-\d+\b", re.IGNORECASE),
        re.compile(r"\bINV-\d+\b", re.IGNORECASE),
        re.compile(r"\bTK-\d+\b", re.IGNORECASE),
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
    ]

    @classmethod
    def analyze(cls, prompt: str) -> DisambiguationResult:
        lower_prompt = prompt.lower()

        # Check if the prompt expresses a mutation/remediation intent
        matches_action = None
        required_targets = []
        for action, targets in cls.DESTRUCTIVE_ACTIONS:
            if action in lower_prompt:
                matches_action = action
                required_targets = targets
                break

        if not matches_action:
            return DisambiguationResult(is_ambiguous=False, missing_fields=[])

        # Check if any explicit entity identifier exists in the prompt
        found_entity = any(regex.search(prompt) for regex in cls.ENTITY_REGEXES)

        if not found_entity:
            # Check for vague pronouns or references: "that customer", "the last order", "the bill"
            vague_indicators = ["the customer", "that order", "last charge", "the bill", "the account", "refund them"]
            if any(ind in lower_prompt for ind in vague_indicators) or len(prompt.split()) < 8:
                return DisambiguationResult(
                    is_ambiguous=True,
                    missing_fields=required_targets,
                    clarification_question=(
                        f"The requested action '{matches_action}' lacks an explicit target. "
                        f"Please specify a Customer ID (e.g. CUST-901), Order ID (e.g. ORD-7702), "
                        f"Invoice ID (e.g. INV-8802), or Support Ticket ID (e.g. TK-4401)."
                    ),
                    suggested_options=[
                        "CUST-901 (Acme Global Corp)",
                        "CUST-902 (Nova Dynamics)",
                        "TK-4401 (Unrecognized charge dispute)",
                    ]
                )

        return DisambiguationResult(is_ambiguous=False, missing_fields=[])
