from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.sandbox_recommendation import (
    SandboxRecommendationNode,
    generate_recommendations,
    _MAX_RECOMMENDATIONS,
)
from isa_cad.core.models.blast_radius import BlastRadiusOutput, ImpactedComponent
from isa_cad.core.models.enums import (
    ComponentTier,
    OptimizationGoal,
    ReviewerStatus,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.recommendation import Recommendation
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate

node = SandboxRecommendationNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def degraded(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.DEGRADED, reason="warn")


def blocked(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.BLOCKED, reason="fail",
                    required_action="fix it")


def cost_rev(status: ReviewerStatus = ReviewerStatus.FAIL, score: float = 0.3):
    return CostReviewerOutput(status=status, score=score, confidence=0.7, recommendation="ok")


def perf_rev(**kwargs) -> PerformanceReviewerOutput:
    base = dict(status=ReviewerStatus.PASS, score=0.7, confidence=0.7, recommendation="ok")
    base.update(kwargs)
    return PerformanceReviewerOutput(**base)


def sec_rev(pii: str = "pass", status: ReviewerStatus = ReviewerStatus.WARNING):
    r = SecurityReviewerOutput(status=status, score=0.5, confidence=0.7, recommendation="ok")
    object.__setattr__(r, "pii_flow_status", pii)
    return r


def blast(high_risk: int = 1) -> BlastRadiusOutput:
    comps = [
        ImpactedComponent(
            id=f"db-{i}", tier=ComponentTier.TIER_1,
            distance=1, criticality_multiplier=2.0,
            impact_score=2.0, risk="io-bottleneck",
        )
        for i in range(high_risk)
    ]
    return BlastRadiusOutput(
        source_component_id="api", max_traversal_depth=3,
        impacted_stable_components=comps,
        summary=f"{high_risk} high-risk",
    )


# ── Output contract ───────────────────────────────────────────────────────────

def test_recommendations_key_present():
    result = node({})
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)


def test_empty_state_no_crash():
    result = node({})
    assert result["recommendations"] == []


def test_state_passthrough():
    result = node({"session_id": "s-1"})
    assert result["session_id"] == "s-1"


def test_final_output_enriched():
    state: AgentState = {
        "cost_review":    cost_rev(),
        "optimization_goal": OptimizationGoal.COST_EFFICIENCY,
        "final_output":   {"decision": "candidate_for_review"},
    }
    result = node(state)
    assert "recommendations" in result["final_output"]


def test_final_output_absent_not_added():
    state: AgentState = {"cost_review": cost_rev()}
    result = node(state)
    assert "final_output" not in result


# ── Max results cap ───────────────────────────────────────────────────────────

def test_max_three_recommendations_returned():
    state: AgentState = {
        "optimization_goal":  OptimizationGoal.BALANCED,
        "cost_review":        cost_rev(),
        "performance_review": perf_rev(db_pressure_risk="high", cold_start_risk="high",
                                        bottleneck_risk="high"),
        "security_gate":      degraded(VetoGateType.SECURITY),
        "security_review":    sec_rev(pii="fail"),
        "blast_radius":       blast(high_risk=2),
        "fidelity_gate":      degraded(VetoGateType.FIDELITY),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED)
    assert len(recs) <= _MAX_RECOMMENDATIONS


# ── Sorted by goal_alignment ──────────────────────────────────────────────────

def test_sorted_by_goal_alignment_descending():
    state: AgentState = {
        "optimization_goal":  OptimizationGoal.COST_EFFICIENCY,
        "cost_review":        cost_rev(),
        "blast_radius":       blast(high_risk=1),
        "performance_review": perf_rev(bottleneck_risk="high"),
    }
    recs = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY)
    scores = [r.goal_alignment for r in recs]
    assert scores == sorted(scores, reverse=True)


# ── rec.lambda-migration ──────────────────────────────────────────────────────

def test_lambda_migration_fires_on_cost_fail():
    state: AgentState = {
        "cost_review": cost_rev(ReviewerStatus.FAIL, 0.2),
    }
    recs = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY)
    ids = [r.id for r in recs]
    assert "rec.lambda-migration" in ids


def test_lambda_migration_fires_on_cost_warning():
    state: AgentState = {
        "cost_review": cost_rev(ReviewerStatus.WARNING, 0.55),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED)
    ids = [r.id for r in recs]
    assert "rec.lambda-migration" in ids


def test_lambda_migration_not_fires_on_pass():
    state: AgentState = {
        "cost_review": CostReviewerOutput(
            status=ReviewerStatus.PASS, score=0.85, confidence=0.8, recommendation="ok"
        ),
    }
    recs = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY)
    ids = [r.id for r in recs]
    assert "rec.lambda-migration" not in ids


def test_lambda_migration_higher_score_for_cost_goal():
    state: AgentState = {"cost_review": cost_rev()}
    recs_cost = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY)
    recs_rel  = generate_recommendations(state, OptimizationGoal.MAX_RELIABILITY)
    score_cost = next(r.goal_alignment for r in recs_cost if r.id == "rec.lambda-migration")
    score_rel  = next(r.goal_alignment for r in recs_rel  if r.id == "rec.lambda-migration")
    assert score_cost > score_rel


# ── rec.read-replica ──────────────────────────────────────────────────────────

def test_read_replica_fires_on_db_pressure_high():
    state: AgentState = {
        "performance_review": perf_rev(db_pressure_risk="high"),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED)
    assert any(r.id == "rec.read-replica" for r in recs)


def test_read_replica_not_fires_when_db_pressure_low():
    state: AgentState = {
        "performance_review": perf_rev(db_pressure_risk="low"),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED)
    assert not any(r.id == "rec.read-replica" for r in recs)


def test_read_replica_higher_score_for_reliability_goal():
    state: AgentState = {"performance_review": perf_rev(db_pressure_risk="high")}
    recs_rel  = generate_recommendations(state, OptimizationGoal.MAX_RELIABILITY)
    recs_cost = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY)
    score_rel  = next(r.goal_alignment for r in recs_rel  if r.id == "rec.read-replica")
    score_cost = next(r.goal_alignment for r in recs_cost if r.id == "rec.read-replica")
    assert score_rel > score_cost


# ── rec.async-decoupling ──────────────────────────────────────────────────────

def test_async_decoupling_fires_on_high_risk_blast():
    state: AgentState = {"blast_radius": blast(high_risk=1)}
    recs = generate_recommendations(state, OptimizationGoal.BALANCED)
    assert any(r.id == "rec.async-decoupling" for r in recs)


def test_async_decoupling_not_fires_when_no_high_risk():
    state: AgentState = {"blast_radius": blast(high_risk=0)}
    recs = generate_recommendations(state, OptimizationGoal.BALANCED)
    assert not any(r.id == "rec.async-decoupling" for r in recs)


def test_async_decoupling_rationale_mentions_count():
    state: AgentState = {"blast_radius": blast(high_risk=3)}
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    rec = next(r for r in recs if r.id == "rec.async-decoupling")
    assert "3" in rec.rationale


# ── rec.auth-middleware ───────────────────────────────────────────────────────

def test_auth_middleware_fires_security_degraded_pii_fail():
    state: AgentState = {
        "security_gate":   degraded(VetoGateType.SECURITY),
        "security_review": sec_rev(pii="fail"),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    assert any(r.id == "rec.auth-middleware" for r in recs)


def test_auth_middleware_fires_on_pii_warning():
    state: AgentState = {
        "security_gate":   degraded(VetoGateType.SECURITY),
        "security_review": sec_rev(pii="warning"),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    assert any(r.id == "rec.auth-middleware" for r in recs)


def test_auth_middleware_not_fires_security_gate_passed():
    state: AgentState = {
        "security_gate":   VetoGate(gate_type=VetoGateType.SECURITY, result=VetoGateResult.PASSED),
        "security_review": sec_rev(pii="fail"),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    assert not any(r.id == "rec.auth-middleware" for r in recs)


# ── rec.provisioned-concurrency ───────────────────────────────────────────────

def test_provisioned_concurrency_fires_on_cold_start_high():
    state: AgentState = {
        "performance_review": perf_rev(cold_start_risk="high"),
    }
    recs = generate_recommendations(state, OptimizationGoal.MAX_RELIABILITY, max_results=7)
    assert any(r.id == "rec.provisioned-concurrency" for r in recs)


def test_provisioned_concurrency_not_fires_without_cold_start():
    state: AgentState = {
        "performance_review": perf_rev(cold_start_risk="low"),
    }
    recs = generate_recommendations(state, OptimizationGoal.MAX_RELIABILITY, max_results=7)
    assert not any(r.id == "rec.provisioned-concurrency" for r in recs)


# ── rec.cdn-caching ───────────────────────────────────────────────────────────

def test_cdn_fires_on_bottleneck_high():
    state: AgentState = {
        "performance_review": perf_rev(bottleneck_risk="high"),
    }
    recs = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY, max_results=7)
    assert any(r.id == "rec.cdn-caching" for r in recs)


def test_cdn_not_fires_on_bottleneck_medium():
    state: AgentState = {
        "performance_review": perf_rev(bottleneck_risk="medium"),
    }
    recs = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY, max_results=7)
    assert not any(r.id == "rec.cdn-caching" for r in recs)


# ── rec.observed-graph-refresh ────────────────────────────────────────────────

def test_observed_refresh_fires_fidelity_degraded():
    state: AgentState = {"fidelity_gate": degraded(VetoGateType.FIDELITY)}
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    assert any(r.id == "rec.observed-graph-refresh" for r in recs)


def test_observed_refresh_fires_fidelity_blocked():
    state: AgentState = {"fidelity_gate": blocked(VetoGateType.FIDELITY)}
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    assert any(r.id == "rec.observed-graph-refresh" for r in recs)


def test_observed_refresh_not_fires_fidelity_passed():
    state: AgentState = {
        "fidelity_gate": VetoGate(gate_type=VetoGateType.FIDELITY, result=VetoGateResult.PASSED)
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=7)
    assert not any(r.id == "rec.observed-graph-refresh" for r in recs)


# ── Recommendation model ──────────────────────────────────────────────────────

def test_recommendation_fields():
    state: AgentState = {"cost_review": cost_rev()}
    recs = generate_recommendations(state, OptimizationGoal.COST_EFFICIENCY)
    rec = recs[0]
    assert isinstance(rec, Recommendation)
    assert rec.id != ""
    assert rec.title != ""
    assert 0.0 <= rec.goal_alignment <= 1.0
    assert isinstance(rec.suggested_changes, list)
    assert len(rec.suggested_changes) > 0
    assert isinstance(rec.expected_improvements, dict)


def test_serialized_to_dict_in_state():
    state: AgentState = {"cost_review": cost_rev()}
    result = node(state)
    for item in result["recommendations"]:
        assert isinstance(item, dict)
        assert "id" in item
        assert "goal_alignment" in item


# ── default goal fallback ─────────────────────────────────────────────────────

def test_no_goal_in_state_defaults_balanced():
    state: AgentState = {"cost_review": cost_rev()}
    result = node(state)
    # Should not raise — defaults to BALANCED
    assert isinstance(result["recommendations"], list)


# ── No duplicate IDs in results ───────────────────────────────────────────────

def test_no_duplicate_recommendation_ids():
    state: AgentState = {
        "optimization_goal":  OptimizationGoal.BALANCED,
        "cost_review":        cost_rev(),
        "performance_review": perf_rev(db_pressure_risk="high", cold_start_risk="high",
                                        bottleneck_risk="high"),
        "blast_radius":       blast(high_risk=2),
        "security_gate":      degraded(VetoGateType.SECURITY),
        "security_review":    sec_rev(pii="fail"),
        "fidelity_gate":      degraded(VetoGateType.FIDELITY),
    }
    recs = generate_recommendations(state, OptimizationGoal.BALANCED, max_results=10)
    ids = [r.id for r in recs]
    assert len(ids) == len(set(ids))
