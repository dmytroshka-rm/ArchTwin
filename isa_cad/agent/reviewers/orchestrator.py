from __future__ import annotations

import concurrent.futures
from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.enums import ReviewerStatus
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    ReviewerOutput,
    SecurityReviewerOutput,
)

from .cost import CostReviewerNode
from .performance import PerformanceReviewerNode
from .security import SecurityReviewerNode


# ── Aggregation helpers ───────────────────────────────────────────────────────

def _aggregate_status(
    cost: CostReviewerOutput,
    perf: PerformanceReviewerOutput,
    sec: SecurityReviewerOutput,
) -> ReviewerStatus:
    """
    Aggregate the three reviewer statuses into one overall status.
    Precedence: FAIL > WARNING > PASS > UNKNOWN.
    Any FAIL → FAIL; any WARNING (no FAIL) → WARNING; else PASS.
    """
    statuses = {cost.status, perf.status, sec.status}
    if ReviewerStatus.FAIL in statuses:
        return ReviewerStatus.FAIL
    if ReviewerStatus.WARNING in statuses:
        return ReviewerStatus.WARNING
    if ReviewerStatus.PASS in statuses:
        return ReviewerStatus.PASS
    return ReviewerStatus.UNKNOWN


def _collect_block_reasons(
    cost: CostReviewerOutput,
    perf: PerformanceReviewerOutput,
    sec: SecurityReviewerOutput,
) -> list[str]:
    """
    Collect human-readable block reasons from all FAIL reviewers.
    A reviewer is a block source if its status is FAIL.
    """
    reasons: list[str] = []

    if cost.status == ReviewerStatus.FAIL:
        reasons.append(f"[cost] {cost.recommendation}")

    if perf.status == ReviewerStatus.FAIL:
        reasons.append(f"[performance] {perf.recommendation}")

    if sec.status == ReviewerStatus.FAIL:
        reasons.append(f"[security] {sec.recommendation}")
        # Surface any critical trust violations explicitly
        for v in sec.trust_boundary_violations:
            reasons.append(f"[security:trust_violation] {v}")

    return reasons


def _combined_confidence(
    cost: CostReviewerOutput,
    perf: PerformanceReviewerOutput,
    sec: SecurityReviewerOutput,
) -> float:
    """Minimum confidence across all reviewers (weakest-link)."""
    return round(min(cost.confidence, perf.confidence, sec.confidence), 4)


def _reviewer_summary(
    cost: CostReviewerOutput,
    perf: PerformanceReviewerOutput,
    sec: SecurityReviewerOutput,
    overall: ReviewerStatus,
    confidence: float,
) -> dict[str, Any]:
    """
    Build the reviewer_summary sub-dict that gets stored in AgentState
    and later consumed by TradeoffAndVetoGateNode.
    """
    return {
        "overall_status":   overall.value,
        "combined_confidence": confidence,
        "reviewers": {
            "cost": {
                "status":      cost.status.value,
                "score":       cost.score,
                "confidence":  cost.confidence,
                "delta_usd":   cost.tco_delta_usd,
                "recommendation": cost.recommendation,
            },
            "performance": {
                "status":       perf.status.value,
                "score":        perf.score,
                "confidence":   perf.confidence,
                "latency_delta": perf.latency_delta,
                "bottleneck_risk": perf.bottleneck_risk,
                "recommendation": perf.recommendation,
            },
            "security": {
                "status":       sec.status.value,
                "score":        sec.score,
                "confidence":   sec.confidence,
                "violations":   len(sec.trust_boundary_violations),
                "pii_status":   sec.pii_flow_status,
                "compliance":   sec.compliance_status,
                "recommendation": sec.recommendation,
            },
        },
        "block_sources": [
            r for r in ("cost", "performance", "security")
            if {
                "cost": cost.status,
                "performance": perf.status,
                "security": sec.status,
            }[r] == ReviewerStatus.FAIL
        ],
    }


# ── Orchestrator node ──────────────────────────────────────────────────────────

class ParallelReviewerNode:
    """
    LangGraph node — runs Cost, Performance and Security reviewers in parallel,
    then merges their outputs into a single AgentState update.

    Parallelism is achieved via ThreadPoolExecutor (each reviewer is a pure
    function with no shared mutable state).  The three sub-state dicts are
    merged and the aggregated signals (overall_status, block_reasons,
    reviewer_summary) are added.

    Outputs written to AgentState:
        cost_review          CostReviewerOutput
        performance_review   PerformanceReviewerOutput
        security_review      SecurityReviewerOutput
        reviewer_summary     dict  (aggregated signals for TradeoffNode)
        is_blocked           bool  (True if any reviewer status is FAIL)
        block_reasons        list[str]
    """

    def __init__(
        self,
        cost_node: CostReviewerNode | None = None,
        perf_node: PerformanceReviewerNode | None = None,
        sec_node:  SecurityReviewerNode | None = None,
        max_workers: int = 3,
    ) -> None:
        self._cost = cost_node or CostReviewerNode()
        self._perf = perf_node or PerformanceReviewerNode()
        self._sec  = sec_node  or SecurityReviewerNode()
        self._max_workers = max_workers

    def __call__(self, state: AgentState) -> AgentState:
        cost_result, perf_result, sec_result = self._run_parallel(state)

        cost: CostReviewerOutput        = cost_result["cost_review"]
        perf: PerformanceReviewerOutput = perf_result["performance_review"]
        sec:  SecurityReviewerOutput    = sec_result["security_review"]

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

    # ── private ───────────────────────────────────────────────────────────────

    def _run_parallel(
        self, state: AgentState
    ) -> tuple[AgentState, AgentState, AgentState]:
        """
        Run all three reviewers concurrently.
        Each reviewer receives a snapshot of the current state (read-only).
        """
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers
        ) as executor:
            f_cost = executor.submit(self._cost, state)
            f_perf = executor.submit(self._perf, state)
            f_sec  = executor.submit(self._sec,  state)

            cost_result = f_cost.result()
            perf_result = f_perf.result()
            sec_result  = f_sec.result()

        return cost_result, perf_result, sec_result
