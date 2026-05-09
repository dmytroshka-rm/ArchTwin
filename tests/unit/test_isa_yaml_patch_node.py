from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.isa_yaml_patch import IsaYamlPatchNode, build_proposal_patch
from isa_cad.core.models.blast_radius import BlastRadiusOutput, ImpactedComponent
from isa_cad.core.models.calibration import CalibrationError, CalibrationResult, SafetyBuffer
from isa_cad.core.models.enums import (
    ComponentTier,
    OptimizationGoal,
    ProposalStatus,
    ReviewerStatus,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.proposal import (
    DesignProposal,
    NonLinearScoring,
    OptimizationWeights,
    RequiredActions,
)
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet
from isa_cad.core.schema.validator import validate_isa_yaml

node = IsaYamlPatchNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_proposal(
    status: ProposalStatus = ProposalStatus.APPROVED,
    score: float = 0.74,
) -> DesignProposal:
    gate_set = VetoGateSet(
        security_gate    = VetoGate(gate_type=VetoGateType.SECURITY,    result=VetoGateResult.PASSED),
        reliability_gate = VetoGate(gate_type=VetoGateType.RELIABILITY, result=VetoGateResult.PASSED),
        compliance_gate  = VetoGate(gate_type=VetoGateType.COMPLIANCE,  result=VetoGateResult.PASSED),
        fidelity_gate    = VetoGate(gate_type=VetoGateType.FIDELITY,    result=VetoGateResult.PASSED),
    )
    scoring = NonLinearScoring(
        recommendation_score=score,
        optimization_weights=OptimizationWeights.from_goal(OptimizationGoal.BALANCED),
        veto_gates=gate_set,
    )
    return DesignProposal(
        id="proposal.test",
        title="Test Proposal",
        status=status,
        optimization_goal=OptimizationGoal.BALANCED,
        baseline_ref="arch.baseline.prod",
        scoring=scoring,
        required_actions=RequiredActions(
            developer=["Set concurrency cap."],
            architect=["Review ADR."],
        ),
    )


def reviewer(cls, status=ReviewerStatus.PASS, score=0.8):
    return cls(status=status, score=score, confidence=0.7, recommendation="ok")


# ── Output contract ───────────────────────────────────────────────────────────

def test_isa_yaml_patch_key_present():
    result = node({"proposal": make_proposal()})
    assert "isa_yaml_patch" in result


def test_no_proposal_returns_empty_patch():
    result = node({})
    assert result["isa_yaml_patch"] == {}


def test_state_passthrough():
    result = node({"proposal": make_proposal(), "session_id": "s-1"})
    assert result["session_id"] == "s-1"


# ── Required top-level fields ─────────────────────────────────────────────────

def test_required_fields_present():
    patch = build_proposal_patch(make_proposal())
    for key in ("id", "title", "status", "optimization_goal", "baseline_ref"):
        assert key in patch, f"Missing required key: {key}"


def test_status_is_string_value():
    patch = build_proposal_patch(make_proposal(status=ProposalStatus.APPROVED))
    assert patch["status"] == "approved"


def test_optimization_goal_is_string_value():
    patch = build_proposal_patch(make_proposal())
    assert patch["optimization_goal"] == "balanced"


# ── non_linear_scoring section ────────────────────────────────────────────────

def test_non_linear_scoring_present():
    patch = build_proposal_patch(make_proposal())
    assert "non_linear_scoring" in patch


def test_non_linear_scoring_fields():
    patch = build_proposal_patch(make_proposal(score=0.74))
    nls = patch["non_linear_scoring"]
    assert nls["recommendation_score"] == pytest.approx(0.74)
    assert "optimization_weights" in nls
    assert "veto_gates" in nls


def test_veto_gates_are_multiplier_floats():
    patch = build_proposal_patch(make_proposal())
    gates = patch["non_linear_scoring"]["veto_gates"]
    for key in ("security_gate", "reliability_gate", "compliance_gate", "fidelity_gate"):
        assert key in gates
        assert gates[key] in (0.0, 0.5, 1.0), f"{key} must be 0.0 / 0.5 / 1.0"


def test_degraded_gate_multiplier_is_half():
    proposal = make_proposal()
    proposal.scoring.veto_gates.security_gate = VetoGate(
        gate_type=VetoGateType.SECURITY, result=VetoGateResult.DEGRADED
    )
    patch = build_proposal_patch(proposal)
    assert patch["non_linear_scoring"]["veto_gates"]["security_gate"] == pytest.approx(0.5)


# ── calibration section ───────────────────────────────────────────────────────

def test_calibration_absent_when_empty():
    proposal = make_proposal()
    proposal.calibration = CalibrationResult(enabled_for_existing_system=False)
    patch = build_proposal_patch(proposal)
    assert "calibration" not in patch


def test_calibration_present_with_errors():
    proposal = make_proposal()
    proposal.calibration = CalibrationResult(
        enabled_for_existing_system=True,
        historical_errors=[
            CalibrationError(metric="cost", predicted_value=1.24, actual_value=1.0),
            CalibrationError(metric="latency", predicted_value=1.18, actual_value=1.0),
        ],
    )
    patch = build_proposal_patch(proposal)
    assert "calibration" in patch
    delta = patch["calibration"]["historical_error_delta"]
    assert "cost" in delta
    assert "latency" in delta


def test_calibration_safety_buffer_included():
    proposal = make_proposal()
    proposal.calibration = CalibrationResult(
        enabled_for_existing_system=True,
        safety_buffer=SafetyBuffer(applied=True, cost_multiplier=1.15, latency_multiplier=1.0),
    )
    patch = build_proposal_patch(proposal)
    assert "safety_buffer" in patch["calibration"]
    assert patch["calibration"]["safety_buffer"]["cost_multiplier"] == pytest.approx(1.15)


def test_calibration_worst_delta_used():
    proposal = make_proposal()
    proposal.calibration = CalibrationResult(
        enabled_for_existing_system=True,
        historical_errors=[
            CalibrationError(metric="cost", predicted_value=1.10, actual_value=1.0),  # 0.10
            CalibrationError(metric="cost", predicted_value=1.30, actual_value=1.0),  # 0.30
        ],
    )
    patch = build_proposal_patch(proposal)
    assert patch["calibration"]["historical_error_delta"]["cost"] == pytest.approx(0.30)


# ── parallel_reviews section ──────────────────────────────────────────────────

def test_parallel_reviews_absent_when_no_reviewers():
    patch = build_proposal_patch(make_proposal())
    assert "parallel_reviews" not in patch


def test_cost_review_in_parallel_reviews():
    proposal = make_proposal()
    proposal.cost_review = reviewer(CostReviewerOutput, score=0.8)
    proposal.cost_review.monthly_current_usd = 1200.0
    proposal.cost_review.monthly_projected_usd = 850.0
    patch = build_proposal_patch(proposal)
    assert "parallel_reviews" in patch
    cost = patch["parallel_reviews"]["cost"]
    assert cost["status"] == "pass"
    assert cost["monthly_current_usd"] == pytest.approx(1200.0)
    assert cost["monthly_projected_usd"] == pytest.approx(850.0)


def test_performance_review_in_parallel_reviews():
    proposal = make_proposal()
    proposal.performance_review = reviewer(PerformanceReviewerOutput, score=0.7)
    proposal.performance_review.bottleneck_risk = "medium"
    patch = build_proposal_patch(proposal)
    perf = patch["parallel_reviews"]["performance"]
    assert perf["bottleneck_risk"] == "medium"
    assert perf["status"] == "pass"


def test_security_review_in_parallel_reviews():
    proposal = make_proposal()
    proposal.security_review = reviewer(SecurityReviewerOutput, score=0.9)
    patch = build_proposal_patch(proposal)
    sec = patch["parallel_reviews"]["security"]
    assert "pii_flow_status" in sec
    assert "compliance_status" in sec


# ── blast_radius section ──────────────────────────────────────────────────────

def test_blast_radius_absent_when_none():
    patch = build_proposal_patch(make_proposal())
    assert "blast_radius" not in patch


def test_blast_radius_present():
    proposal = make_proposal()
    proposal.blast_radius = BlastRadiusOutput(
        source_component_id="api",
        max_traversal_depth=3,
        impacted_stable_components=[
            ImpactedComponent(
                id="db", tier=ComponentTier.TIER_1,
                distance=1, criticality_multiplier=2.0,
                impact_score=2.0, risk="io-bottleneck",
                mitigations=["connection pooling"],
            )
        ],
        summary="1 component impacted",
    )
    patch = build_proposal_patch(proposal)
    assert "blast_radius" in patch
    br = patch["blast_radius"]
    assert br["source_component_id"] == "api"
    assert len(br["impacted_stable_components"]) == 1
    comp = br["impacted_stable_components"][0]
    assert comp["tier"] == "tier_1"
    assert comp["criticality_multiplier"] == pytest.approx(2.0)
    assert "connection pooling" in comp["mitigations"]


# ── checkpointing section ─────────────────────────────────────────────────────

def test_checkpointing_always_present():
    patch = build_proposal_patch(make_proposal())
    assert "checkpointing" in patch
    assert patch["checkpointing"]["checkpoint_required"] is False


def test_checkpointing_no_checkpoint_minimal():
    patch = build_proposal_patch(make_proposal(), checkpoint=None)
    cp = patch["checkpointing"]
    assert cp["checkpoint_required"] is False
    assert "checkpoint_id" not in cp


# ── required_actions section ──────────────────────────────────────────────────

def test_required_actions_present():
    patch = build_proposal_patch(make_proposal())
    assert "required_actions" in patch


def test_required_actions_all_personas():
    patch = build_proposal_patch(make_proposal())
    ra = patch["required_actions"]
    for key in ("developer", "architect", "security_ops", "data_fidelity"):
        assert key in ra
        assert isinstance(ra[key], list)


def test_required_actions_content():
    proposal = make_proposal()
    patch = build_proposal_patch(proposal)
    assert "Set concurrency cap." in patch["required_actions"]["developer"]
    assert "Review ADR." in patch["required_actions"]["architect"]


# ── JSON Schema validation ────────────────────────────────────────────────────

def test_minimal_proposal_passes_schema():
    patch = build_proposal_patch(make_proposal())
    result = validate_isa_yaml({"design_proposals": [patch]})
    assert result.valid, f"Schema errors: {result.errors}"


def test_proposal_with_all_sections_passes_schema():
    proposal = make_proposal()
    proposal.cost_review = reviewer(CostReviewerOutput)
    proposal.cost_review.monthly_current_usd = 1200.0
    proposal.cost_review.monthly_projected_usd = 850.0
    proposal.performance_review = reviewer(PerformanceReviewerOutput)
    proposal.performance_review.bottleneck_risk = "medium"
    proposal.security_review = reviewer(SecurityReviewerOutput)
    proposal.calibration = CalibrationResult(
        enabled_for_existing_system=True,
        historical_errors=[
            CalibrationError(metric="cost", predicted_value=1.24, actual_value=1.0),
        ],
        safety_buffer=SafetyBuffer(applied=True, cost_multiplier=1.15, latency_multiplier=1.0),
    )
    proposal.blast_radius = BlastRadiusOutput(
        source_component_id="api", max_traversal_depth=3,
        impacted_stable_components=[], summary="0 impacted",
    )
    patch = build_proposal_patch(proposal)
    result = validate_isa_yaml({"design_proposals": [patch]})
    assert result.valid, f"Schema errors: {result.errors}"


def test_blocked_proposal_passes_schema():
    patch = build_proposal_patch(make_proposal(status=ProposalStatus.BLOCKED))
    result = validate_isa_yaml({"design_proposals": [patch]})
    assert result.valid, f"Schema errors: {result.errors}"


# ── Node integration ──────────────────────────────────────────────────────────

def test_node_writes_isa_yaml_patch():
    state: AgentState = {"proposal": make_proposal()}
    result = node(state)
    assert isinstance(result["isa_yaml_patch"], dict)
    assert result["isa_yaml_patch"]["id"] == "proposal.test"


def test_node_enriches_final_output():
    state: AgentState = {
        "proposal":     make_proposal(),
        "final_output": {"decision": "approved"},
    }
    result = node(state)
    fo = result["final_output"]
    assert "isa_yaml_patch"  in fo
    assert "isa_yaml_valid"  in fo
    assert "isa_yaml_errors" in fo


def test_node_final_output_valid_flag():
    state: AgentState = {
        "proposal":     make_proposal(),
        "final_output": {},
    }
    result = node(state)
    assert result["final_output"]["isa_yaml_valid"] is True


def test_node_absent_final_output_not_added():
    state: AgentState = {"proposal": make_proposal()}
    result = node(state)
    assert "final_output" not in result
