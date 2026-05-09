from __future__ import annotations

"""
isa_cad/agent/reviewers/llm/security_llm.py
=============================================
LLM-backed Security Reviewer.
"""

from typing import Any

from isa_cad.core.models.enums import ReviewerStatus, ReviewerType
from isa_cad.core.models.reviewer import Finding, SecurityReviewerOutput

from .base import LLMReviewerBase
from .prompts import SECURITY_REVIEWER_SYSTEM


class LLMSecurityReviewer(LLMReviewerBase):
    """LLM-backed security reviewer using Claude or GPT-4o."""

    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.SECURITY

    @property
    def system_prompt(self) -> str:
        return SECURITY_REVIEWER_SYSTEM

    def _parse_output(self, data: dict[str, Any]) -> SecurityReviewerOutput:
        status_raw = str(data.get("status", "unknown")).lower()
        status = (
            ReviewerStatus(status_raw)
            if status_raw in ReviewerStatus._value2member_map_
            else ReviewerStatus.UNKNOWN
        )

        findings = [
            Finding(
                severity=f.get("severity", "info"),
                title=f.get("title", ""),
                description=f.get("description", ""),
                recommendation=f.get("recommendation"),
            )
            for f in (data.get("findings") or [])
            if isinstance(f, dict)
        ]

        return SecurityReviewerOutput(
            reviewer=ReviewerType.SECURITY,
            status=status,
            score=float(data.get("score", 0.5)),
            confidence=float(data.get("confidence", 0.5)),
            trust_boundary_violations=list(data.get("trust_boundary_violations") or []),
            pii_flow_status=str(data.get("pii_flow_status", "unknown")),
            compliance_status=str(data.get("compliance_status", "unknown")),
            public_exposure_risk=data.get("public_exposure_risk"),
            iam_scope_risk=data.get("iam_scope_risk"),
            recommendation=str(data.get("recommendation", "")),
            findings=findings,
            assumptions=list(data.get("assumptions") or []),
            missing_inputs=list(data.get("missing_inputs") or []),
        )

    def _fallback(self, reason: str) -> SecurityReviewerOutput:
        return SecurityReviewerOutput(
            reviewer=ReviewerType.SECURITY,
            status=ReviewerStatus.UNKNOWN,
            score=0.5,
            confidence=0.0,
            pii_flow_status="unknown",
            compliance_status="unknown",
            recommendation=f"LLM reviewer unavailable: {reason}",
            missing_inputs=[reason],
        )
