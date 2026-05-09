from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.reflect_decide import ReflectAndDecideNode, _APPROVE_THRESHOLD
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.core.models.calibration import CalibrationResult, SafetyBuffer
from isa_cad.core.models.enums import (
    OptimizationGoal,
    OutputMode,
    ProposalStatus,
    ReviewerStatus,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.proposal import DesignProposal, NonLinearScoring, OptimizationWeights
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet

node = ReflectAndDecideNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def passed_gate(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.PASSED, reason="ok")


def degraded_gate(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.DEGRADED, reason="warn")


def blocked_gate(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.BLOCKED, reason="blocked",
                    required_action="fix it")


def make_proposal(score: float = 0.80, status: ProposalStatus = ProposalStatus.CANDIDATE_FOR_REVIEW) -> DesignProposal:
    scoring = NonLinearScoring(
        recommendation_score=score,
        optimization_weights=OptimizationWeights(),
        veto_gates=VetoGateSet(),
        raw_weighted_sum=0.5,
    )
    return DesignProposal(
        id="proposal.test",
        title="Test Proposal",
        status=status,
        optimization_goal=OptimizationGoal.BALANCED,
        baseline_ref="arch.baseline.prod",
        scoring=scoring,
    )


def make_cal_output(
    human_review: bool = False,
    buffer_applied: bool = False,
) -> CalibrationLoopOutput:
    sb = SafetyBuffer(applied=buffer_applied, cost_multiplier=1.15 if buffer_applied else 1.0)
    result = CalibrationResult(safety_buffer=sb)
    out = CalibrationLoopOutput(result=result, summary="cal summary")
    out.human_review_required = human_review
    return out


def make_blast_radius(summary: str = "2 components impacted") -> BlastRadiusOutput:
    return BlastRadiusOutput(
        source_component_id="api",
        max_traversal_depth=3,
        impacted_stable_components=[],
        summary=summary,
    )


def base_state(
    score: float = 0.80,
    is_blocked: bool = False,
    block_reasons: list[str] | None = None,
    fidelity: VetoGateResult = VetoGateResult.PASSED,
    human_review: bool = False,
) -> AgentState:
    return {
        "proposal":              make_proposal(score),
        "is_blocked":            is_blocked,
        "block_reasons":         block_reasons or [],
        "blast_radius":          make_blast_radius(),
        "calibration_loop_output": make_cal_output(human_review=human_review),
        "fidelity_gate":         VetoGate(gate_type=VetoGateType.FIDELITY, result=fidelity),
    }


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_mode_key_present():
    result = node(base_state())
    assert "output_mode" in result


def test_final_output_key_present():
    result = node(base_state())
    assert "final_output" in result
    assert isinstance(result["final_output"], dict)


def test_final_output_required_keys():
    result = node(base_state())
    fo = result["final_output"]
    for key in (
        "proposal_id", "decision", "recommendation_score", "output_mode",
        "is_blocked", "block_reasons", "veto_product", "reviewer_signals",
        "blast_radius_summary", "high_risk_components", "total_blast_impact",
        "calibration_summary", "human_review_required", "safety_buffer_applied",
    ):
        assert key in fo, f"Missing key: {key}"


# ── output_mode determination ─────────────────────────────────────────────────

def test_fidelity_passed_gives_final_forecast():
    result = node(base_state(fidelity=VetoGateResult.PASSED))
    assert result["output_mode"] == OutputMode.FINAL_FORECAST


def test_fidelity_degraded_gives_exploratory():
    result = node(base_state(fidelity=VetoGateResult.DEGRADED))
    assert result["output_mode"] == OutputMode.EXPLORATORY_ESTIMATE


def test_fidelity_blocked_gives_exploratory():
    result = node(base_state(fidelity=VetoGateResult.BLOCKED))
    assert result["output_mode"] == OutputMode.EXPLORATORY_ESTIMATE


def test_no_fidelity_gate_gives_exploratory():
    state: AgentState = {
        "proposal":    make_proposal(0.80),
        "is_blocked":  False,
        "block_reasons": [],
    }
    result = node(state)
    assert result["output_mode"] == OutputMode.EXPLORATORY_ESTIMATE


def test_output_mode_reflected_in_final_output():
    result = node(base_state(fidelity=VetoGateResult.PASSED))
    assert result["final_output"]["output_mode"] == OutputMode.FINAL_FORECAST.value


# ── Decision: BLOCKED ─────────────────────────────────────────────────────────

def test_is_blocked_true_decision_blocked():
    result = node(base_state(score=0.0, is_blocked=True))
    assert result["final_output"]["decision"] == ProposalStatus.BLOCKED.value


def test_blocked_proposal_status_updated():
    state = base_state(score=0.0, is_blocked=True)
    result = node(state)
    assert result["proposal"].status == ProposalStatus.BLOCKED


def test_blocked_score_does_not_matter():
    # Even with high score, is_blocked overrides
    result = node(base_state(score=0.99, is_blocked=True))
    assert result["final_output"]["decision"] == ProposalStatus.BLOCKED.value


# ── Decision: CANDIDATE_FOR_REVIEW (human review required) ───────────────────

def test_human_review_required_prevents_approve():
    result = node(base_state(score=0.90, human_review=True))
    assert result["final_output"]["decision"] == ProposalStatus.CANDIDATE_FOR_REVIEW.value


def test_human_review_required_reflected_in_final_output():
    result = node(base_state(human_review=True))
    assert result["final_output"]["human_review_required"] is True


def test_no_human_review_not_required():
    result = node(base_state(score=0.80, human_review=False))
    assert result["final_output"]["human_review_required"] is False


# ── Decision: APPROVED ────────────────────────────────────────────────────────

def test_score_at_threshold_is_approved():
    result = node(base_state(score=_APPROVE_THRESHOLD))
    assert result["final_output"]["decision"] == ProposalStatus.APPROVED.value


def test_score_above_threshold_is_approved():
    result = node(base_state(score=0.85))
    assert result["final_output"]["decision"] == ProposalStatus.APPROVED.value


def test_approved_proposal_status_updated():
    state = base_state(score=0.80)
    result = node(state)
    assert result["proposal"].status == ProposalStatus.APPROVED


# ── Decision: CANDIDATE_FOR_REVIEW (low score) ───────────────────────────────

def test_score_below_threshold_candidate():
    result = node(base_state(score=_APPROVE_THRESHOLD - 0.01))
    assert result["final_output"]["decision"] == ProposalStatus.CANDIDATE_FOR_REVIEW.value


def test_score_zero_not_blocked_is_candidate():
    # Score=0 but is_blocked=False → CANDIDATE_FOR_REVIEW not BLOCKED
    result = node(base_state(score=0.0, is_blocked=False))
    assert result["final_output"]["decision"] == ProposalStatus.CANDIDATE_FOR_REVIEW.value


def test_score_just_below_threshold_candidate():
    result = node(base_state(score=0.69))
    assert result["final_output"]["decision"] == ProposalStatus.CANDIDATE_FOR_REVIEW.value


# ── Recommendation score in final_output ─────────────────────────────────────

def test_recommendation_score_propagated():
    result = node(base_state(score=0.75))
    assert result["final_output"]["recommendation_score"] == pytest.approx(0.75)


def test_no_proposal_score_is_zero():
    state: AgentState = {"is_blocked": False, "block_reasons": []}
    result = node(state)
    assert result["final_output"]["recommendation_score"] == 0.0


# ── block_reasons passthrough ─────────────────────────────────────────────────

def test_block_reasons_preserved():
    state = base_state(is_blocked=True, block_reasons=["[security_gate] violation"])
    result = node(state)
    assert "[security_gate] violation" in result["block_reasons"]
    assert "[security_gate] violation" in result["final_output"]["block_reasons"]


# ── Blast radius signals ──────────────────────────────────────────────────────

def test_blast_radius_summary_in_final_output():
    state = base_state()
    state["blast_radius"] = make_blast_radius("3 components at risk")
    result = node(state)
    assert result["final_output"]["blast_radius_summary"] == "3 components at risk"


def test_no_blast_radius_empty_summary():
    state: AgentState = {"is_blocked": False, "block_reasons": []}
    result = node(state)
    assert result["final_output"]["blast_radius_summary"] == ""
    assert result["final_output"]["high_risk_components"] == 0


# ── Calibration signals ───────────────────────────────────────────────────────

def test_calibration_summary_in_final_output():
    state = base_state()
    result = node(state)
    assert result["final_output"]["calibration_summary"] == "cal summary"


def test_safety_buffer_applied_propagated():
    state = base_state()
    state["calibration_loop_output"] = make_cal_output(buffer_applied=True)
    result = node(state)
    assert result["final_output"]["safety_buffer_applied"] is True


def test_safety_buffer_not_applied_propagated():
    state = base_state()
    state["calibration_loop_output"] = make_cal_output(buffer_applied=False)
    result = node(state)
    assert result["final_output"]["safety_buffer_applied"] is False


# ── Reviewer signals ──────────────────────────────────────────────────────────

def test_reviewer_signals_from_proposal():
    proposal = make_proposal(0.80)
    proposal.cost_review = CostReviewerOutput(
        status=ReviewerStatus.PASS, score=0.75, confidence=0.8, recommendation="ok"
    )
    proposal.performance_review = PerformanceReviewerOutput(
        status=ReviewerStatus.PASS, score=0.65, confidence=0.7, recommendation="ok"
    )
    state: AgentState = {
        "proposal":    proposal,
        "is_blocked":  False,
        "block_reasons": [],
    }
    result = node(state)
    sigs = result["final_output"]["reviewer_signals"]
    assert sigs["cost_score"] == pytest.approx(0.75)
    assert sigs["performance_score"] == pytest.approx(0.65)


def test_reviewer_signals_fallback_to_state():
    state: AgentState = {
        "proposal":    make_proposal(0.80),
        "is_blocked":  False,
        "block_reasons": [],
        "security_review": SecurityReviewerOutput(
            status=ReviewerStatus.PASS, score=0.90, confidence=0.8, recommendation="ok"
        ),
    }
    result = node(state)
    assert result["final_output"]["reviewer_signals"]["security_score"] == pytest.approx(0.90)


def test_reviewer_signals_none_when_absent():
    state: AgentState = {"is_blocked": False, "block_reasons": []}
    result = node(state)
    sigs = result["final_output"]["reviewer_signals"]
    assert sigs["cost_score"] is None
    assert sigs["performance_score"] is None
    assert sigs["security_score"] is None


# ── State passthrough ─────────────────────────────────────────────────────────

def test_existing_state_keys_preserved():
    state = base_state()
    state["session_id"] = "sess-reflect"
    result = node(state)
    assert result["session_id"] == "sess-reflect"
    assert "final_output" in result


def test_no_proposal_graceful():
    state: AgentState = {"is_blocked": False, "block_reasons": []}
    result = node(state)
    assert result["final_output"]["proposal_id"] is None
    assert result["final_output"]["decision"] == ProposalStatus.CANDIDATE_FOR_REVIEW.value
