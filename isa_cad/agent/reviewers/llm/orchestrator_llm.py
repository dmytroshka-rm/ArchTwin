from __future__ import annotations

"""
isa_cad/agent/reviewers/llm/orchestrator_llm.py
=================================================
LLM-backed parallel reviewer orchestrator.

Drop-in replacement for ``ParallelReviewerNode`` — uses ``LLMCostReviewer``,
``LLMPerformanceReviewer``, and ``LLMSecurityReviewer`` instead of the
rule-based implementations.

The three LLM reviewers run concurrently via ``ThreadPoolExecutor`` (same as
the rule-based orchestrator) so the wall-clock time is ~max(reviewer_latency).
"""

import concurrent.futures
from typing import Any

from langchain_core.language_models import BaseChatModel

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.reviewers.orchestrator import (
    _aggregate_status,
    _collect_block_reasons,
    _combined_confidence,
    _reviewer_summary,
)
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.enums import ReviewerStatus

from .cost_llm import LLMCostReviewer
from .performance_llm import LLMPerformanceReviewer
from .security_llm import LLMSecurityReviewer


class LLMParallelReviewerNode:
    """
    LangGraph node — runs all three LLM-backed reviewers in parallel.

    Accepts an optional shared ``llm`` instance to avoid constructing
    three separate model clients (useful in tests and cost-aware scenarios).
    When ``llm=None``, each reviewer constructs its own model lazily.

    Outputs are identical to ``ParallelReviewerNode``:
        cost_review, performance_review, security_review,
        reviewer_summary, is_blocked, block_reasons
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        max_workers: int = 3,
    ) -> None:
        self._cost = LLMCostReviewer(llm=llm)
        self._perf = LLMPerformanceReviewer(llm=llm)
        self._sec  = LLMSecurityReviewer(llm=llm)
        self._max_workers = max_workers

    def __call__(self, state: AgentState) -> AgentState:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers
        ) as executor:
            f_cost = executor.submit(self._cost, state)
            f_perf = executor.submit(self._perf, state)
            f_sec  = executor.submit(self._sec,  state)

            cost_state = f_cost.result()
            perf_state = f_perf.result()
            sec_state  = f_sec.result()

        cost: CostReviewerOutput        = cost_state["cost_review"]
        perf: PerformanceReviewerOutput = perf_state["performance_review"]
        sec:  SecurityReviewerOutput    = sec_state["security_review"]

        overall    = _aggregate_status(cost, perf, sec)
        reasons    = _collect_block_reasons(cost, perf, sec)
        confidence = _combined_confidence(cost, perf, sec)
        summary    = _reviewer_summary(cost, perf, sec, overall, confidence)

        return {
            **state,
            "cost_review":        cost,
            "performance_review": perf,
            "security_review":    sec,
            "reviewer_summary":   summary,
            "is_blocked":         overall == ReviewerStatus.FAIL,
            "block_reasons":      reasons,
        }
