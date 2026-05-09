from __future__ import annotations

"""
isa_cad/agent/reviewers/llm/cost_llm.py
=========================================
LLM-backed Cost Reviewer.

Drop-in replacement for ``CostReviewerNode``.  Implements the same
``__call__(state) -> state`` interface so it can be injected into
``build_graph(parallel_reviewer_node=...)``.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel

from isa_cad.core.models.enums import ReviewerStatus, ReviewerType
from isa_cad.core.models.reviewer import CostReviewerOutput, Finding

from .base import LLMReviewerBase
from .prompts import COST_REVIEWER_SYSTEM


class LLMCostReviewer(LLMReviewerBase):
    """LLM-backed cost reviewer using Claude or GPT-4o."""

    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.COST

    @property
    def system_prompt(self) -> str:
        return COST_REVIEWER_SYSTEM

    def _parse_output(self, data: dict[str, Any]) -> CostReviewerOutput:
        status_raw = str(data.get("status", "unknown")).lower()
        status = ReviewerStatus(status_raw) if status_raw in ReviewerStatus._value2member_map_ else ReviewerStatus.UNKNOWN

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

        return CostReviewerOutput(
            reviewer=ReviewerType.COST,
            status=status,
            score=float(data.get("score", 0.5)),
            confidence=float(data.get("confidence", 0.5)),
            tco_delta_usd=data.get("tco_delta_usd"),
            recommendation=str(data.get("recommendation", "")),
            findings=findings,
            assumptions=list(data.get("assumptions") or []),
            missing_inputs=list(data.get("missing_inputs") or []),
        )

    def _fallback(self, reason: str) -> CostReviewerOutput:
        return CostReviewerOutput(
            reviewer=ReviewerType.COST,
            status=ReviewerStatus.UNKNOWN,
            score=0.5,
            confidence=0.0,
            recommendation=f"LLM reviewer unavailable: {reason}",
            missing_inputs=[reason],
        )
