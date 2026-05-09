from __future__ import annotations

from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.logging import get_logger
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput

_log = get_logger(__name__)
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.core.models.enums import OutputMode, ProposalStatus, VetoGateResult
from isa_cad.core.models.proposal import DesignProposal
from isa_cad.core.models.veto import VetoGate


# Score at or above this → APPROVED (all other conditions must also pass)
_APPROVE_THRESHOLD: float = 0.70


def _determine_output_mode(fidelity_gate: VetoGate | None) -> OutputMode:
    """
    FINAL_FORECAST only when fidelity gate explicitly PASSED.
    Any degradation, block, or absence → EXPLORATORY_ESTIMATE (pessimistic).
    """
    if fidelity_gate is not None and fidelity_gate.result == VetoGateResult.PASSED:
        return OutputMode.FINAL_FORECAST
    return OutputMode.EXPLORATORY_ESTIMATE


def _reviewer_signals(proposal: DesignProposal | None, state: AgentState) -> dict[str, Any]:
    """Collect per-reviewer scores from proposal or raw state."""
    cost_r = (proposal.cost_review if proposal else None) or state.get("cost_review")
    perf_r = (proposal.performance_review if proposal else None) or state.get("performance_review")
    sec_r  = (proposal.security_review  if proposal else None) or state.get("security_review")

    reviewer_summary = state.get("reviewer_summary") or {}

    return {
        "cost_score":        cost_r.score if cost_r else None,
        "performance_score": perf_r.score if perf_r else None,
        "security_score":    sec_r.score  if sec_r  else None,
        "overall_status":    reviewer_summary.get("overall_status", "unknown"),
    }


def _build_final_output(
    *,
    proposal: DesignProposal | None,
    decision: ProposalStatus,
    output_mode: OutputMode,
    is_blocked: bool,
    block_reasons: list[str],
    blast_radius: BlastRadiusOutput | None,
    cal_output: CalibrationLoopOutput | None,
    human_review_required: bool,
    reviewer_signals: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the Decision-Grade Output Contract (Section 0.1).
    This dict is the canonical top-level response for external consumers.
    """
    score = proposal.scoring.recommendation_score if proposal else 0.0
    veto_product = proposal.scoring.veto_gates.product if proposal else 0.0

    return {
        "proposal_id":           proposal.id if proposal else None,
        "decision":              decision.value,
        "recommendation_score":  score,
        "output_mode":           output_mode.value,
        "is_blocked":            is_blocked,
        "block_reasons":         block_reasons,
        "veto_product":          veto_product,
        "reviewer_signals":      reviewer_signals,
        "blast_radius_summary":  blast_radius.summary if blast_radius else "",
        "high_risk_components":  blast_radius.high_risk_count if blast_radius else 0,
        "total_blast_impact":    blast_radius.total_impact_score if blast_radius else 0.0,
        "calibration_summary":   cal_output.summary if cal_output else "",
        "human_review_required": human_review_required,
        "safety_buffer_applied": (
            cal_output.result.safety_buffer.applied if cal_output else False
        ),
    }


class ReflectAndDecideNode:
    """
    LangGraph node — final APPROVE / BLOCK / CANDIDATE_FOR_REVIEW decision.
    Section 6.1 of the convention (Reflect & Decide).

    Decision rules (evaluated in order):
        1. is_blocked        → BLOCKED            (any gate was BLOCKED)
        2. human_review_required → CANDIDATE_FOR_REVIEW (security false negative history)
        3. score ≥ 0.70      → APPROVED
        4. otherwise         → CANDIDATE_FOR_REVIEW

    output_mode:
        FINAL_FORECAST        when fidelity_gate is PASSED
        EXPLORATORY_ESTIMATE  when fidelity_gate is DEGRADED, BLOCKED, or absent

    Reads:
        state["proposal"]               DesignProposal + scoring from TradeoffAndVetoGateNode
        state["is_blocked"]             bool from TradeoffAndVetoGateNode
        state["block_reasons"]          list[str] from TradeoffAndVetoGateNode
        state["blast_radius"]           BlastRadiusOutput from BlastRadiusNode
        state["calibration_loop_output"]CalibrationLoopOutput from CalibrationNode
        state["fidelity_gate"]          VetoGate for output_mode determination
        state["reviewer_summary"]       aggregated reviewer signals
        state["cost_review"]            fallback for reviewer signals
        state["performance_review"]     fallback for reviewer signals
        state["security_review"]        fallback for reviewer signals

    Writes:
        state["output_mode"]   OutputMode
        state["final_output"]  Decision-Grade Output Contract dict (Section 0.1)
        state["is_blocked"]    unchanged (re-written for clarity)
        state["block_reasons"] unchanged (re-written for clarity)
    """

    def __call__(self, state: AgentState) -> AgentState:
        proposal: DesignProposal | None = state.get("proposal")
        is_blocked: bool = state.get("is_blocked", False)
        block_reasons: list[str] = list(state.get("block_reasons") or [])
        blast_radius: BlastRadiusOutput | None = state.get("blast_radius")
        cal_output: CalibrationLoopOutput | None = state.get("calibration_loop_output")
        fidelity_gate: VetoGate | None = state.get("fidelity_gate")

        output_mode = _determine_output_mode(fidelity_gate)

        human_review_required = (
            cal_output.human_review_required if cal_output else False
        )

        score = proposal.scoring.recommendation_score if proposal else 0.0

        if is_blocked:
            decision = ProposalStatus.BLOCKED
        elif human_review_required:
            decision = ProposalStatus.CANDIDATE_FOR_REVIEW
        elif score >= _APPROVE_THRESHOLD:
            decision = ProposalStatus.APPROVED
        else:
            decision = ProposalStatus.CANDIDATE_FOR_REVIEW

        # Update proposal status in-place so it reflects the final verdict
        if proposal is not None:
            proposal.status = decision

        signals = _reviewer_signals(proposal, state)

        final_output = _build_final_output(
            proposal=proposal,
            decision=decision,
            output_mode=output_mode,
            is_blocked=is_blocked,
            block_reasons=block_reasons,
            blast_radius=blast_radius,
            cal_output=cal_output,
            human_review_required=human_review_required,
            reviewer_signals=signals,
        )

        _log.info(
            "node.done",
            node="reflect_decide",
            decision=decision.value,
            score=round(score, 4),
            output_mode=output_mode.value,
            is_blocked=is_blocked,
        )
        return {
            **state,
            "output_mode":   output_mode,
            "final_output":  final_output,
            "is_blocked":    is_blocked,
            "block_reasons": block_reasons,
        }
