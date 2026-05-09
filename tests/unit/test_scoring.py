from __future__ import annotations

import pytest

from isa_cad.core.math_models.scoring import GainVector, RecommendationScorer, ScoringInput
from isa_cad.core.models.enums import (
    OptimizationGoal,
    ReviewerStatus,
    ReviewerType,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.proposal import OptimizationWeights
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet

scorer = RecommendationScorer()


# ── GainVector ────────────────────────────────────────────────────────────────

def test_gain_vector_clamp_upper():
    g = GainVector(cost=1.5, performance=2.0, reliability=-2.0, security=0.5)
    c = g.clamp()
    assert c.cost == 1.0
    assert c.performance == 1.0
    assert c.reliability == -1.0
    assert c.security == 0.5


def test_gain_vector_zero_is_neutral():
    g = GainVector()
    assert g.cost == g.performance == g.reliability == g.security == 0.0


# ── Pure formula: SUM * PRODUCT, all gates pass ───────────────────────────────

def test_all_gains_max_all_gates_pass():
    # max improvement on all dims, all gates pass → raw_sum = 1.0 → normalized = 1.0
    gain = GainVector(cost=1.0, performance=1.0, reliability=1.0, security=1.0)
    gates = VetoGateSet()  # all passed
    result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))

    assert result.veto_product == 1.0
    assert not result.is_blocked
    assert result.recommendation_score == pytest.approx(1.0, abs=0.001)


def test_all_gains_zero_neutral_score():
    # No change from baseline → normalized = 0.5, all gates pass → score ≈ 0.5
    gain = GainVector(cost=0.0, performance=0.0, reliability=0.0, security=0.0)
    gates = VetoGateSet()
    result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))

    assert result.recommendation_score == pytest.approx(0.5, abs=0.001)


def test_all_gains_negative_low_score():
    # All metrics degrade → raw_sum = -1.0 → normalized = 0.0 → score ≈ 0.0
    gain = GainVector(cost=-1.0, performance=-1.0, reliability=-1.0, security=-1.0)
    gates = VetoGateSet()
    result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))

    assert result.recommendation_score == pytest.approx(0.0, abs=0.001)


# ── Veto gate: BLOCKED collapses score to 0 ──────────────────────────────────

def test_blocked_security_veto_score_zero():
    gain = GainVector(cost=1.0, performance=1.0, reliability=1.0, security=1.0)
    gates = VetoGateSet(
        security_gate=VetoGate(gate_type=VetoGateType.SECURITY, result=VetoGateResult.BLOCKED)
    )
    result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))

    assert result.recommendation_score == 0.0
    assert result.is_blocked
    assert result.veto_product == 0.0
    assert any("BLOCKED" in n for n in result.notes)


def test_blocked_compliance_veto_score_zero():
    gain = GainVector(cost=0.8, performance=0.6, reliability=0.7, security=0.9)
    gates = VetoGateSet(
        compliance_gate=VetoGate(gate_type=VetoGateType.COMPLIANCE, result=VetoGateResult.BLOCKED)
    )
    result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.COST_EFFICIENCY))

    assert result.recommendation_score == 0.0
    assert result.is_blocked


# ── Veto gate: DEGRADED halves score ─────────────────────────────────────────

def test_degraded_gate_halves_score():
    gain = GainVector(cost=1.0, performance=1.0, reliability=1.0, security=1.0)
    gates = VetoGateSet(
        reliability_gate=VetoGate(gate_type=VetoGateType.RELIABILITY, result=VetoGateResult.DEGRADED)
    )
    full_result  = scorer.compute(ScoringInput(gain, VetoGateSet(), OptimizationGoal.BALANCED))
    half_result  = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))

    assert half_result.recommendation_score == pytest.approx(
        full_result.recommendation_score * 0.5, abs=0.001
    )
    assert half_result.veto_product == 0.5


def test_two_degraded_gates_quarter_score():
    gain = GainVector(cost=1.0, performance=1.0, reliability=1.0, security=1.0)
    gates = VetoGateSet(
        security_gate=VetoGate(gate_type=VetoGateType.SECURITY, result=VetoGateResult.DEGRADED),
        reliability_gate=VetoGate(gate_type=VetoGateType.RELIABILITY, result=VetoGateResult.DEGRADED),
    )
    full_result  = scorer.compute(ScoringInput(gain, VetoGateSet(), OptimizationGoal.BALANCED))
    quarter_result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))

    assert quarter_result.veto_product == pytest.approx(0.25, abs=0.001)
    assert quarter_result.recommendation_score == pytest.approx(
        full_result.recommendation_score * 0.25, abs=0.001
    )


# ── Optimization goal changes weights ────────────────────────────────────────

def test_cost_efficiency_goal_rewards_cost_gain():
    # Cost gain high, others neutral
    gain = GainVector(cost=1.0, performance=0.0, reliability=0.0, security=0.0)
    gates = VetoGateSet()

    cost_result = scorer.compute(
        ScoringInput(gain, gates, OptimizationGoal.COST_EFFICIENCY)
    )
    balanced_result = scorer.compute(
        ScoringInput(gain, gates, OptimizationGoal.BALANCED)
    )
    # cost_efficiency weights cost at 0.45 vs balanced at 0.25 → higher score
    assert cost_result.recommendation_score > balanced_result.recommendation_score


def test_max_reliability_goal_rewards_reliability_gain():
    gain = GainVector(cost=0.0, performance=0.0, reliability=1.0, security=0.0)
    gates = VetoGateSet()

    rel_result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.MAX_RELIABILITY))
    balanced_result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))
    assert rel_result.recommendation_score > balanced_result.recommendation_score


# ── to_non_linear_scoring ─────────────────────────────────────────────────────

def test_to_non_linear_scoring_roundtrip():
    gain = GainVector(cost=0.5, performance=0.3, reliability=0.4, security=0.6)
    gates = VetoGateSet()
    result = scorer.compute(ScoringInput(gain, gates, OptimizationGoal.BALANCED))
    nls = result.to_non_linear_scoring()

    assert nls.recommendation_score == result.recommendation_score
    assert nls.raw_weighted_sum == result.raw_weighted_sum
    assert nls.veto_gates is gates


# ── compute_from_reviewers ────────────────────────────────────────────────────

def test_from_reviewers_all_pass_high_score():
    cost   = CostReviewerOutput(reviewer=ReviewerType.COST,        status=ReviewerStatus.PASS, score=0.9)
    perf   = PerformanceReviewerOutput(reviewer=ReviewerType.PERFORMANCE, status=ReviewerStatus.PASS, score=0.85)
    sec    = SecurityReviewerOutput(reviewer=ReviewerType.SECURITY, status=ReviewerStatus.PASS, score=0.95)
    gates  = VetoGateSet()

    result = scorer.compute_from_reviewers(cost, perf, sec, gates, OptimizationGoal.BALANCED)
    assert result.recommendation_score > 0.6
    assert not result.is_blocked


def test_from_reviewers_security_fail_blocked():
    cost   = CostReviewerOutput(reviewer=ReviewerType.COST,        status=ReviewerStatus.PASS, score=1.0)
    perf   = PerformanceReviewerOutput(reviewer=ReviewerType.PERFORMANCE, status=ReviewerStatus.PASS, score=1.0)
    sec    = SecurityReviewerOutput(reviewer=ReviewerType.SECURITY, status=ReviewerStatus.FAIL, score=0.0)

    gates = VetoGateSet(
        security_gate=VetoGate(gate_type=VetoGateType.SECURITY, result=VetoGateResult.BLOCKED)
    )
    result = scorer.compute_from_reviewers(cost, perf, sec, gates, OptimizationGoal.BALANCED)

    assert result.recommendation_score == 0.0
    assert result.is_blocked


def test_from_reviewers_none_inputs_neutral():
    gates = VetoGateSet()
    result = scorer.compute_from_reviewers(None, None, None, gates, OptimizationGoal.BALANCED)
    # All gains = 0.0 → neutral score ≈ 0.5
    assert result.recommendation_score == pytest.approx(0.5, abs=0.001)


def test_from_reviewers_score_breakdown_keys():
    cost  = CostReviewerOutput(reviewer=ReviewerType.COST, status=ReviewerStatus.PASS, score=0.7)
    gates = VetoGateSet()
    result = scorer.compute_from_reviewers(cost, None, None, gates)

    assert "cost" in result.score_breakdown
    assert "performance" in result.score_breakdown
    assert "reliability" in result.score_breakdown
    assert "security" in result.score_breakdown


# ── Custom weight override ────────────────────────────────────────────────────

def test_custom_weights_override():
    gain = GainVector(cost=1.0, performance=0.0, reliability=0.0, security=0.0)
    gates = VetoGateSet()
    custom_weights = OptimizationWeights(cost=1.0, performance=0.0, reliability=0.0, security=0.0)

    result = scorer.compute(ScoringInput(gain, gates, weights=custom_weights))
    # With full weight on cost and max cost gain → normalized = 1.0 → score = 1.0
    assert result.recommendation_score == pytest.approx(1.0, abs=0.001)
    assert result.weights.cost == 1.0
