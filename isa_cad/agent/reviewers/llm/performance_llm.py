from __future__ import annotations

"""
isa_cad/agent/reviewers/llm/performance_llm.py
================================================
LLM-backed Performance Reviewer.
"""

from typing import Any

from isa_cad.core.models.enums import ReviewerStatus, ReviewerType
from isa_cad.core.models.reviewer import Finding, PerformanceReviewerOutput

from .base import LLMReviewerBase
from .prompts import PERFORMANCE_REVIEWER_SYSTEM


class LLMPerformanceReviewer(LLMReviewerBase):
    """LLM-backed performance reviewer using Claude or GPT-4o."""

    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.PERFORMANCE

    @property
    def system_prompt(self) -> str:
        return PERFORMANCE_REVIEWER_SYSTEM

    def _parse_output(self, data: dict[str, Any]) -> PerformanceReviewerOutput:
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

        return PerformanceReviewerOutput(
            reviewer=ReviewerType.PERFORMANCE,
            status=status,
            score=float(data.get("score", 0.5)),
            confidence=float(data.get("confidence", 0.5)),
            latency_delta=data.get("latency_delta"),
            bottleneck_risk=data.get("bottleneck_risk"),
            recommendation=str(data.get("recommendation", "")),
            findings=findings,
            assumptions=list(data.get("assumptions") or []),
            missing_inputs=list(data.get("missing_inputs") or []),
        )

    def _fallback(self, reason: str) -> PerformanceReviewerOutput:
        return PerformanceReviewerOutput(
            reviewer=ReviewerType.PERFORMANCE,
            status=ReviewerStatus.UNKNOWN,
            score=0.5,
            confidence=0.0,
            recommendation=f"LLM reviewer unavailable: {reason}",
            missing_inputs=[reason],
        )
