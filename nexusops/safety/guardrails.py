"""
NexusOps Safety Guardrails, Injection Defense & Grounding Verification.

Provides multi-layer security validation:
1. Input Prompt Injection & Jailbreak Detection
2. Sensitive PII / Credential Sanitization
3. Output Grounding & Tool Hallucination Verification
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Set


@dataclass
class GuardrailResult:
    is_safe: bool
    risk_score: float  # 0.0 (safe) to 1.0 (malicious)
    flags: List[str]
    sanitized_text: str


class PromptInjectionGuard:
    """Detects adversarial jailbreak attempts, delimiter hijacking, and prompt injection."""

    INJECTION_PATTERNS = [
        (r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions", "INSTRUCTION_OVERRIDE"),
        (r"(?i)you\s+are\s+now\s+(unfiltered|dan|root|godmode|jailbreak)", "ROLE_HIJACK"),
        (r"(?i)system\s+prompt\s+override", "SYSTEM_OVERRIDE"),
        (r"(?i)bypass\s+(safety|security|authorization|hitl|guardrails)", "AUTH_BYPASS"),
        (r"(?i)drop\s+table|delete\s+from|update\s+.*set\s+.*password", "SQL_INJECTION"),
        (r"(?i)<\s*script\b|javascript:|onerror\s*=", "XSS_PAYLOAD"),
        (r"(?i)transfer\s+all\s+funds|refund\s+without\s+approval", "MALICIOUS_BUSINESS_LOGIC"),
    ]

    @classmethod
    def evaluate(cls, text: str) -> GuardrailResult:
        flags = []
        score = 0.0

        for pattern, flag in cls.INJECTION_PATTERNS:
            if re.search(pattern, text):
                flags.append(flag)
                score += 0.50

        score = min(score, 1.0)
        is_safe = score < 0.40

        return GuardrailResult(
            is_safe=is_safe,
            risk_score=round(score, 2),
            flags=flags,
            sanitized_text=text
        )


class PIIRedactor:
    """Masks payment card PANs, SSNs, and API keys before logging or model ingestion."""

    # Credit card regex (13 to 19 digits)
    CARD_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b|\b\d{15,16}\b")
    # SSN regex
    SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    # API key patterns (bearer tokens, secret keys)
    API_KEY_REGEX = re.compile(r"(?i)(?:bearer|key|token|secret)\s*[:=]\s*([a-zA-Z0-9_\-\.]{16,})")

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return text
        # Redact cards
        text = cls.CARD_REGEX.sub(r"[REDACTED_CARD_NUMBER]", text)
        # Redact SSNs
        text = cls.SSN_REGEX.sub(r"[REDACTED_SSN]", text)
        # Redact secrets
        text = cls.API_KEY_REGEX.sub(r"key=[REDACTED_SECRET]", text)
        return text


class GroundingVerifier:
    """Verifies that final agent responses are grounded in verified tool outputs (anti-hallucination)."""

    @classmethod
    def extract_entities(cls, text: str) -> Set[str]:
        """Extracts candidate entities: IDs, dollar amounts, emails, normalized numbers."""
        entities = set()
        # Dollar amounts ($199.99, $50) and also add stripped numeric float values
        for amt in re.findall(r"\$\d+(?:\.\d{2})?", text):
            entities.add(amt.strip().lower())
            val = amt.replace("$", "").strip()
            try:
                entities.add(f"{float(val):.2f}")
                entities.add(f"{float(val):.1f}")
            except Exception:
                pass
        # Numbers like 189.5 or 1450.0
        for num in re.findall(r"\b\d+(?:\.\d{1,2})?\b", text):
            try:
                fval = float(num)
                if fval > 10.0:  # ignore small single digit indices
                    entities.add(f"{fval:.2f}")
                    entities.add(f"{fval:.1f}")
                    entities.add(f"${fval:.2f}")
            except Exception:
                pass
        # IDs like INV-1002, CH_9921, TK-442
        for ref_id in re.findall(r"\b[A-Z]{2,4}[-_]\d{3,8}\b", text):
            entities.add(ref_id.strip().upper())
        # Emails
        for email in re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", text):
            entities.add(email.strip().lower())
        return entities

    @classmethod
    def verify(cls, response_text: str, tool_observations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Cross-checks referenced entities in the response against the tool observations.
        Returns a grounding report with confidence score and hallucination flags.
        """
        obs_text = " ".join([str(obs) for obs in tool_observations])
        response_entities = cls.extract_entities(response_text)
        obs_entities = cls.extract_entities(obs_text)

        if not response_entities:
            return {
                "grounding_score": 1.0,
                "verified_entities": [],
                "unverified_entities": [],
                "is_grounded": True,
                "verdict": "No factual financial or entity claims to verify"
            }

        verified = [e for e in response_entities if e in obs_entities]
        unverified = [e for e in response_entities if e not in obs_entities]

        grounding_score = len(verified) / len(response_entities) if response_entities else 1.0
        is_grounded = grounding_score >= 0.75

        return {
            "grounding_score": round(grounding_score, 2),
            "verified_entities": verified,
            "unverified_entities": unverified,
            "is_grounded": is_grounded,
            "verdict": "Grounded in system data" if is_grounded else f"Flagged: {len(unverified)} unverified claims"
        }
