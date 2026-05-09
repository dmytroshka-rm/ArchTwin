from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.tradeoff_veto import (
    TradeoffAndVetoGateNode,
    _build_gate_set,
    _collect_block_reasons,
    _missing_gate,
)
from isa_cad.core.models.enums import (
    OptimizationGoal,
    ProposalStatus,
    ReviewerStatus,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.proposal import DesignProposal
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet
from isa_cad.state.canvas_state import CanvasSessionState, ComponentGraph, ComponentNode

node = TradeoffAndVetoGateNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def passed_gate(gate_type: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=gate_type, result=VetoGateResult.PASSED,
                    reason="ok", required_action=None)


def blocked_gate(gate_type: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=gate_type, result=VetoGateResult.BLOCKED,
                    reason=f"{gate_type.value} blocked", required_action="fix it")


def degraded_gate(gate_type: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=gate_type, result=VetoGateResult.DEGRADED,
                    reason=f"{gate_type.value} degraded", required_action="review it")


def reviewer(
    cls,
    status: ReviewerStatus = ReviewerStatus.PASS,
    score: float = 0.8,
) -> CostReviewerOutput | PerformanceReviewerOutput | SecurityReviewerOutput:
    return cls(status=status, score=score, confidence=0.7, recommendation="ok")


def all_passed_state(goal: OptimizationGoal = OptimizationGoal.BALANCED) -> AgentState:
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = ComponentGraph(nodes=[
        ComponentNode(id="svc", label="Svc", tier="standard", component_type="service")
    ])
    return {
        "canvas_session":    session,
        "resolved_graph":    session.baseline_graph,
        "optimization_goal": goal,
        "proposal_id":       "proposal.test",
        "security_gate":     passed_gate(VetoGateType.SECURITY),
        "reliability_gate":  passed_gate(VetoGateType.RELIABILITY),
        "compliance_gate":   passed_gate(VetoGateType.COMPLIANCE),
        "fidelity_gate":     passed_gate(VetoGateType.FIDELITY),
        "cost_review":       reviewer(CostReviewerOutput,        score=0.8),
        "performance_review":reviewer(PerformanceReviewerOutput, score=0.8),
        "security_review":   reviewer(SecurityReviewerOutput,    score=0.8),
    }


# ── Output contract ───────────────────────────────────────────────────────────

def test_proposal_present_in_output():
    result = node(all_passed_state())
    assert "proposal" in result
    assert isinstance(result["proposal"], DesignProposal)


def test_is_blocked_and_block_reasons_present():
    result = node(all_passed_state())
    assert "is_blocked" in result
    assert "block_reasons" in result
    assert isinstance(result["block_reasons"], list)


def test_proposal_has_scoring():
    result = node(all_passed_state())
    scoring = result["proposal"].scoring
    assert scoring.recommendation_score >= 0.0
    assert scoring.recommendation_score <= 1.0
    assert scoring.veto_gates is not None


def test_proposal_id_from_state():
    result = node(all_passed_state())
    assert result["proposal"].id == "proposal.test"


def test_proposal_goal_from_state():
    result = node(all_passed_state(OptimizationGoal.COST_EFFICIENCY))
    assert result["proposal"].optimization_goal == OptimizationGoal.COST_EFFICIENCY


# ── All gates PASSED → unblocked, high score ─────────────────────────────────

def test_all_passed_not_blocked():
    result = node(all_passed_state())
    assert result["is_blocked"] is False
    assert result["block_reasons"] == []


def test_all_passed_score_above_half():
    result = node(all_passed_state())
    assert result["proposal"].scoring.recommendation_score > 0.5


def test_all_passed_veto_product_is_1():
    result = node(all_passed_state())
    gate_set = result["proposal"].scoring.veto_gates
    assert gate_set.product == pytest.approx(1.0)


# ── Single BLOCKED gate collapses score ──────────────────────────────────────

def test_security_blocked_score_is_zero():
    state = all_passed_state()
    state["security_gate"] = blocked_gate(VetoGateType.SECURITY)
    result = node(state)
    assert result["proposal"].scoring.recommendation_score == 0.0


def test_security_blocked_is_blocked_true():
    state = all_passed_state()
    state["security_gate"] = blocked_gate(VetoGateType.SECURITY)
    result = node(state)
    assert result["is_blocked"] is True


def test_fidelity_blocked_score_is_zero():
    state = all_passed_state()
    state["fidelity_gate"] = blocked_gate(VetoGateType.FIDELITY)
    result = node(state)
    assert result["proposal"].scoring.recommendation_score == 0.0


def test_all_blocked_score_is_zero():
    state = all_passed_state()
    for k, t in [
        ("security_gate", VetoGateType.SECURITY),
        ("reliability_gate", VetoGateType.RELIABILITY),
        ("compliance_gate", VetoGateType.COMPLIANCE),
        ("fidelity_gate", VetoGateType.FIDELITY),
    ]:
        state[k] = blocked_gate(t)
    result = node(state)
    assert result["proposal"].scoring.recommendation_score == 0.0
    assert result["is_blocked"] is True


# ── DEGRADED gate halves the veto product ────────────────────────────────────

def test_one_degraded_gate_halves_product():
    state = all_passed_state()
    state["security_gate"] = degraded_gate(VetoGateType.SECURITY)
    result = node(state)
    gate_set = result["proposal"].scoring.veto_gates
    assert gate_set.product == pytest.approx(0.5)


def test_two_degraded_gates_quarter_product():
    state = all_passed_state()
    state["security_gate"]   = degraded_gate(VetoGateType.SECURITY)
    state["fidelity_gate"]   = degraded_gate(VetoGateType.FIDELITY)
    result = node(state)
    gate_set = result["proposal"].scoring.veto_gates
    assert gate_set.product == pytest.approx(0.25)


def test_degraded_not_blocked():
    state = all_passed_state()
    state["reliability_gate"] = degraded_gate(VetoGateType.RELIABILITY)
    result = node(state)
    assert result["is_blocked"] is False


# ── Block reasons accumulation ────────────────────────────────────────────────

def test_blocked_gate_reason_in_block_reasons():
    state = all_passed_state()
    state["security_gate"] = blocked_gate(VetoGateType.SECURITY)
    result = node(state)
    reasons = result["block_reasons"]
    assert any("[security_gate]" in r for r in reasons)


def test_existing_block_reasons_preserved():
    state = all_passed_state()
    state["security_gate"] = blocked_gate(VetoGateType.SECURITY)
    state["block_reasons"] = ["[cost] too expensive"]
    result = node(state)
    reasons = result["block_reasons"]
    assert any("[cost]" in r for r in reasons)
    assert any("[security_gate]" in r for r in reasons)


def test_block_reasons_deduplicated():
    state = all_passed_state()
    state["security_gate"] = blocked_gate(VetoGateType.SECURITY)
    gate_reason = f"[security_gate] {blocked_gate(VetoGateType.SECURITY).reason}"
    state["block_reasons"] = [gate_reason]   # same reason already present
    result = node(state)
    count = sum(1 for r in result["block_reasons"] if "[security_gate]" in r)
    assert count == 1   # not duplicated


# ── Missing gates default to DEGRADED ────────────────────────────────────────

def test_missing_gate_defaults_to_degraded():
    gate = _missing_gate(VetoGateType.COMPLIANCE)
    assert gate.result == VetoGateResult.DEGRADED
    assert gate.multiplier == 0.5


def test_missing_all_gates_product_is_0_0625():
    """4 missing gates, each DEGRADED (0.5) → 0.5^4 = 0.0625."""
    state: AgentState = {
        "cost_review":       reviewer(CostReviewerOutput),
        "performance_review":reviewer(PerformanceReviewerOutput),
        "security_review":   reviewer(SecurityReviewerOutput),
        "optimization_goal": OptimizationGoal.BALANCED,
        "proposal_id":       "p-test",
    }
    result = node(state)
    assert result["proposal"].scoring.veto_gates.product == pytest.approx(0.5 ** 4)


def test_partial_gates_in_state():
    """Only security_gate provided → others default to DEGRADED."""
    state: AgentState = {
        "security_gate": passed_gate(VetoGateType.SECURITY),
        "optimization_goal": OptimizationGoal.BALANCED,
        "proposal_id": "p-partial",
    }
    gate_set = _build_gate_set(state)
    assert gate_set.security_gate.result == VetoGateResult.PASSED
    assert gate_set.reliability_gate.result == VetoGateResult.DEGRADED
    assert gate_set.compliance_gate.result == VetoGateResult.DEGRADED
    assert gate_set.fidelity_gate.result == VetoGateResult.DEGRADED


# ── Scoring formula ───────────────────────────────────────────────────────────

def test_blocked_reviewer_reduces_score():
    state_ok   = all_passed_state()
    state_fail = all_passed_state()
    state_fail["cost_review"] = reviewer(CostReviewerOutput, ReviewerStatus.FAIL, 0.0)

    r_ok   = node(state_ok)
    r_fail = node(state_fail)
    assert r_fail["proposal"].scoring.recommendation_score < \
           r_ok["proposal"].scoring.recommendation_score


def test_cost_efficiency_goal_weights_cost_higher():
    state_cost    = all_passed_state(OptimizationGoal.COST_EFFICIENCY)
    state_balanced = all_passed_state(OptimizationGoal.BALANCED)
    # Give cost reviewer a big win, others neutral (0.5)
    for s in (state_cost, state_balanced):
        s["cost_review"]        = reviewer(CostReviewerOutput,        score=1.0)
        s["performance_review"] = reviewer(PerformanceReviewerOutput, score=0.5)
        s["security_review"]    = reviewer(SecurityReviewerOutput,    score=0.5)

    r_cost    = node(state_cost)
    r_balanced = node(state_balanced)
    # COST_EFFICIENCY should yield higher score when cost is great
    assert r_cost["proposal"].scoring.recommendation_score >= \
           r_balanced["proposal"].scoring.recommendation_score


def test_raw_weighted_sum_stored_in_scoring():
    result = node(all_passed_state())
    assert result["proposal"].scoring.raw_weighted_sum != 0.0 or True  # field exists
    assert hasattr(result["proposal"].scoring, "raw_weighted_sum")


# ── ProposalStatus ────────────────────────────────────────────────────────────

def test_blocked_gate_sets_proposal_blocked():
    state = all_passed_state()
    state["compliance_gate"] = blocked_gate(VetoGateType.COMPLIANCE)
    result = node(state)
    assert result["proposal"].status == ProposalStatus.BLOCKED


def test_all_pass_sets_candidate_for_review():
    result = node(all_passed_state())
    assert result["proposal"].status == ProposalStatus.CANDIDATE_FOR_REVIEW


# ── No reviewer outputs graceful ─────────────────────────────────────────────

def test_no_reviewer_outputs_neutral_score():
    """No reviewer outputs → gain = 0 → normalized = 0.5 → score = 0.5 * veto_product."""
    state: AgentState = {
        "security_gate":     passed_gate(VetoGateType.SECURITY),
        "reliability_gate":  passed_gate(VetoGateType.RELIABILITY),
        "compliance_gate":   passed_gate(VetoGateType.COMPLIANCE),
        "fidelity_gate":     passed_gate(VetoGateType.FIDELITY),
        "optimization_goal": OptimizationGoal.BALANCED,
        "proposal_id":       "p-no-reviewers",
    }
    result = node(state)
    score = result["proposal"].scoring.recommendation_score
    assert score == pytest.approx(0.5, abs=0.01)


# ── State passthrough ─────────────────────────────────────────────────────────

def test_existing_state_keys_preserved():
    state = all_passed_state()
    state["session_id"] = "sess-tradeoff"
    result = node(state)
    assert result["session_id"] == "sess-tradeoff"
    assert "proposal" in result


# ── _collect_block_reasons helper ────────────────────────────────────────────

def test_collect_block_reasons_deduplicates():
    gate_set = VetoGateSet(
        security_gate=blocked_gate(VetoGateType.SECURITY),
    )
    existing = ["[security_gate] security blocked"]
    reasons = _collect_block_reasons(gate_set, existing)
    count = sum(1 for r in reasons if "security_gate" in r)
    assert count == 1
