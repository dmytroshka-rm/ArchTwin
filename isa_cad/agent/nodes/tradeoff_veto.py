from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.math_models.scoring import RecommendationScorer, ScoringResult
from isa_cad.core.models.enums import OptimizationGoal, ProposalStatus, VetoGateResult, VetoGateType
from isa_cad.core.models.proposal import DesignProposal, NonLinearScoring, OptimizationWeights
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet


_scorer = RecommendationScorer()

# Default gate when a gate is absent from state (pessimistic: DEGRADED, G_j=0.5)
def _missing_gate(gate_type: VetoGateType) -> VetoGate:
    return VetoGate(
        gate_type=gate_type,
        result=VetoGateResult.DEGRADED,
        reason=f"{gate_type.value} gate not evaluated — defaulting to DEGRADED.",
        required_action=f"Run {gate_type.value.capitalize()}VetoGate before TradeoffAndVetoGateNode.",
    )


def _build_gate_set(state: AgentState) -> VetoGateSet:
    """
    Assemble a VetoGateSet from individual gate state keys.
    Missing gates default to DEGRADED (not PASSED) to prevent false-positive scores.
    """
    return VetoGateSet(
        security_gate=state.get("security_gate")    or _missing_gate(VetoGateType.SECURITY),
        reliability_gate=state.get("reliability_gate") or _missing_gate(VetoGateType.RELIABILITY),
        compliance_gate=state.get("compliance_gate")  or _missing_gate(VetoGateType.COMPLIANCE),
        fidelity_gate=state.get("fidelity_gate")    or _missing_gate(VetoGateType.FIDELITY),
    )


def _proposal_status(gate_set: VetoGateSet) -> ProposalStatus:
    if gate_set.is_blocked:
        return ProposalStatus.BLOCKED
    if gate_set.active_warnings:
        return ProposalStatus.CANDIDATE_FOR_REVIEW
    return ProposalStatus.CANDIDATE_FOR_REVIEW


def _collect_block_reasons(
    gate_set: VetoGateSet,
    existing_reasons: list[str],
) -> list[str]:
    """
    Merge block reasons from veto gates with any already in state.
    Deduplicate while preserving order.
    """
    gate_reasons = [
        f"[{g.gate_type.value}_gate] {g.reason}"
        for g in gate_set.active_blocks
        if g.reason
    ]
    combined = gate_reasons + [r for r in existing_reasons if r not in gate_reasons]
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for r in combined:
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result


def _build_proposal(
    state: AgentState,
    gate_set: VetoGateSet,
    scoring: ScoringResult,
    status: ProposalStatus,
) -> DesignProposal:
    """Assemble a DesignProposal from all available state signals."""
    session   = state.get("canvas_session")
    goal      = state.get("optimization_goal", OptimizationGoal.BALANCED)
    cal       = state.get("calibration_result")

    session_id  = session.session_id  if session else "unknown"
    baseline    = session.baseline_ref if session else "unknown"
    proposal_id = state.get("proposal_id", f"proposal.{session_id}")

    return DesignProposal(
        id=proposal_id,
        title=f"Proposal for {proposal_id}",
        status=status,
        optimization_goal=goal,
        canvas_session_id=session_id,
        baseline_ref=baseline,
        calibration=cal or __import__(
            "isa_cad.core.models.calibration", fromlist=["CalibrationResult"]
        ).CalibrationResult(),
        scoring=scoring.to_non_linear_scoring(),
        cost_review=state.get("cost_review"),
        performance_review=state.get("performance_review"),
        security_review=state.get("security_review"),
    )


class TradeoffAndVetoGateNode:
    """
    LangGraph node — assembles all veto gate results into a VetoGateSet,
    computes the non-linear recommendation score, and builds a DesignProposal.

    Formula (Section 3.1):
        recommendation_score = SUM_i(w_i * gain_i) * PRODUCT_j(G_j)

    Where:
        w_i   — weights from OptimizationGoal preset
        gain_i — reviewer score mapped to [-1, +1]
        G_j   — veto gate multiplier (PASSED=1.0, DEGRADED=0.5, BLOCKED=0.0)

    If any G_j == 0.0 → score collapses to 0.0 and proposal is BLOCKED.

    Reads:
        security_gate, reliability_gate, compliance_gate, fidelity_gate
        cost_review, performance_review, security_review
        optimization_goal, canvas_session, calibration_result, proposal_id
        block_reasons (existing)

    Writes:
        proposal           (DesignProposal)
        is_blocked         (bool)
        block_reasons      (list[str] — merged gate reasons + existing)
    """

    def __call__(self, state: AgentState) -> AgentState:
        goal = state.get("optimization_goal", OptimizationGoal.BALANCED)

        gate_set = _build_gate_set(state)

        scoring = _scorer.compute_from_reviewers(
            cost_output=state.get("cost_review"),
            perf_output=state.get("performance_review"),
            security_output=state.get("security_review"),
            veto_gates=gate_set,
            optimization_goal=goal,
        )

        status  = _proposal_status(gate_set)
        proposal = _build_proposal(state, gate_set, scoring, status)

        is_blocked = gate_set.is_blocked
        block_reasons = _collect_block_reasons(
            gate_set,
            state.get("block_reasons") or [],
        )

        return {
            **state,
            "proposal":      proposal,
            "is_blocked":    is_blocked,
            "block_reasons": block_reasons,
        }
