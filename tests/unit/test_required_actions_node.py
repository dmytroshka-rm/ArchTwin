from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.required_actions import RequiredActionsNode
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.core.models.calibration import CalibrationResult, SafetyBuffer
from isa_cad.core.models.enums import OptimizationGoal, VetoGateResult, VetoGateType
from isa_cad.core.models.proposal import DesignProposal, NonLinearScoring, RequiredActions
from isa_cad.core.models.veto import VetoGate, VetoGateSet

node = RequiredActionsNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def passed(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.PASSED, reason="ok")


def degraded(t: VetoGateType, reason: str = "warning") -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.DEGRADED, reason=reason)


def blocked(t: VetoGateType, reason: str = "critical") -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.BLOCKED,
                    reason=reason, required_action="fix it")


def make_proposal() -> DesignProposal:
    return DesignProposal(
        id="proposal.test",
        title="Test",
        baseline_ref="arch.prod",
        optimization_goal=OptimizationGoal.BALANCED,
        scoring=NonLinearScoring(),
    )


def make_cal(human_review: bool = False, buffer: bool = False) -> CalibrationLoopOutput:
    sb = SafetyBuffer(applied=buffer, cost_multiplier=1.15 if buffer else 1.0)
    out = CalibrationLoopOutput(result=CalibrationResult(safety_buffer=sb), summary="")
    out.human_review_required = human_review
    return out


def make_blast(high_risk: int = 0) -> BlastRadiusOutput:
    from isa_cad.core.models.blast_radius import ImpactedComponent
    from isa_cad.core.models.enums import ComponentTier
    comps = []
    for i in range(high_risk):
        comps.append(ImpactedComponent(
            id=f"db-{i}", tier=ComponentTier.TIER_1,
            distance=1, criticality_multiplier=2.0,
            impact_score=2.0, risk="io-bottleneck",
        ))
    return BlastRadiusOutput(
        source_component_id="api",
        max_traversal_depth=3,
        impacted_stable_components=comps,
        summary=f"{high_risk} high-risk components",
    )


# ── Output contract ───────────────────────────────────────────────────────────

def test_empty_state_no_crash():
    result = node({})
    assert isinstance(result, dict)


def test_proposal_required_actions_updated():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "security_gate": blocked(VetoGateType.SECURITY),
    }
    node(state)
    assert len(proposal.required_actions.security_ops) > 0


def test_final_output_enriched_when_present():
    state: AgentState = {
        "security_gate": blocked(VetoGateType.SECURITY),
        "final_output": {"decision": "blocked"},
    }
    result = node(state)
    assert "required_actions" in result["final_output"]


def test_final_output_absent_no_key_added():
    state: AgentState = {"security_gate": blocked(VetoGateType.SECURITY)}
    result = node(state)
    assert "final_output" not in result


def test_state_passthrough():
    state: AgentState = {"session_id": "s-123", "security_gate": passed(VetoGateType.SECURITY)}
    result = node(state)
    assert result["session_id"] == "s-123"


# ── All gates PASSED → empty actions ─────────────────────────────────────────

def test_all_gates_passed_no_actions():
    state: AgentState = {
        "security_gate":    passed(VetoGateType.SECURITY),
        "reliability_gate": passed(VetoGateType.RELIABILITY),
        "compliance_gate":  passed(VetoGateType.COMPLIANCE),
        "fidelity_gate":    passed(VetoGateType.FIDELITY),
    }
    result = node(state)
    proposal = make_proposal()
    state["proposal"] = proposal
    node(state)
    ra = proposal.required_actions
    assert ra.developer == []
    assert ra.architect == []
    assert ra.security_ops == []
    assert ra.data_fidelity == []


# ── Security gate ─────────────────────────────────────────────────────────────

def test_security_blocked_populates_security_ops():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "security_gate": blocked(VetoGateType.SECURITY, "trust boundary violation"),
    }
    node(state)
    assert any("trust boundary" in a for a in proposal.required_actions.security_ops)


def test_security_blocked_populates_developer():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "security_gate": blocked(VetoGateType.SECURITY),
    }
    node(state)
    assert len(proposal.required_actions.developer) > 0


def test_security_degraded_populates_security_ops_only():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "security_gate": degraded(VetoGateType.SECURITY, "exposure warning"),
    }
    node(state)
    assert len(proposal.required_actions.security_ops) > 0
    assert proposal.required_actions.developer == []


def test_security_blocked_contains_block_keyword():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "security_gate": blocked(VetoGateType.SECURITY),
    }
    node(state)
    assert any("BLOCK" in a for a in proposal.required_actions.security_ops)


# ── Reliability gate ──────────────────────────────────────────────────────────

def test_reliability_blocked_populates_architect():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "reliability_gate": blocked(VetoGateType.RELIABILITY, "P95 exceeded"),
    }
    node(state)
    assert any("BLOCK" in a for a in proposal.required_actions.architect)


def test_reliability_blocked_populates_developer():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "reliability_gate": blocked(VetoGateType.RELIABILITY),
    }
    node(state)
    assert len(proposal.required_actions.developer) > 0


def test_reliability_degraded_populates_architect():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "reliability_gate": degraded(VetoGateType.RELIABILITY),
    }
    node(state)
    assert len(proposal.required_actions.architect) > 0
    assert proposal.required_actions.developer == []


# ── Compliance gate ───────────────────────────────────────────────────────────

def test_compliance_blocked_populates_data_fidelity():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "compliance_gate": blocked(VetoGateType.COMPLIANCE, "PII residency failure"),
    }
    node(state)
    assert any("BLOCK" in a for a in proposal.required_actions.data_fidelity)


def test_compliance_blocked_populates_security_ops():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "compliance_gate": blocked(VetoGateType.COMPLIANCE),
    }
    node(state)
    assert any("compliance" in a.lower() for a in proposal.required_actions.security_ops)


def test_compliance_degraded_populates_data_fidelity():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "compliance_gate": degraded(VetoGateType.COMPLIANCE),
    }
    node(state)
    assert len(proposal.required_actions.data_fidelity) > 0


# ── Fidelity gate ─────────────────────────────────────────────────────────────

def test_fidelity_blocked_populates_developer():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "fidelity_gate": blocked(VetoGateType.FIDELITY, "confidence too low"),
    }
    node(state)
    assert any("BLOCK" in a for a in proposal.required_actions.developer)


def test_fidelity_degraded_populates_developer():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "fidelity_gate": degraded(VetoGateType.FIDELITY),
    }
    node(state)
    assert any("refresh" in a.lower() for a in proposal.required_actions.developer)


# ── Blast radius signals ──────────────────────────────────────────────────────

def test_high_risk_components_architect_action():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "blast_radius": make_blast(high_risk=2),
    }
    node(state)
    assert any("2" in a and "Tier-1" in a for a in proposal.required_actions.architect)


def test_no_high_risk_no_blast_architect_action():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "blast_radius": make_blast(high_risk=0),
    }
    node(state)
    assert proposal.required_actions.architect == []


# ── Calibration signals ───────────────────────────────────────────────────────

def test_human_review_required_security_ops_and_architect():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "calibration_loop_output": make_cal(human_review=True),
    }
    node(state)
    assert any("human review" in a.lower() for a in proposal.required_actions.security_ops)
    assert any("human review" in a.lower() for a in proposal.required_actions.architect)


def test_safety_buffer_applied_architect_action():
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "calibration_loop_output": make_cal(buffer=True),
    }
    node(state)
    assert any("safety buffer" in a.lower() for a in proposal.required_actions.architect)


def test_no_calibration_no_extra_actions():
    proposal = make_proposal()
    state: AgentState = {"proposal": proposal}
    node(state)
    assert proposal.required_actions.security_ops == []
    assert proposal.required_actions.architect == []


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_same_action_not_duplicated():
    """Running the node twice should not produce duplicate entries."""
    proposal = make_proposal()
    state: AgentState = {
        "proposal": proposal,
        "calibration_loop_output": make_cal(human_review=True),
    }
    node(state)
    first_count = len(proposal.required_actions.security_ops)
    node(state)  # run again — same state
    # Proposal is replaced entirely each run, so count stays stable
    assert len(proposal.required_actions.security_ops) == first_count


# ── final_output["required_actions"] structure ────────────────────────────────

def test_required_actions_dict_has_all_personas():
    state: AgentState = {
        "security_gate": blocked(VetoGateType.SECURITY),
        "final_output": {"decision": "blocked"},
    }
    result = node(state)
    ra = result["final_output"]["required_actions"]
    for key in ("developer", "architect", "security_ops", "data_fidelity"):
        assert key in ra, f"Missing persona key: {key}"


def test_required_actions_dict_values_are_lists():
    state: AgentState = {
        "security_gate": blocked(VetoGateType.SECURITY),
        "final_output": {},
    }
    result = node(state)
    ra = result["final_output"]["required_actions"]
    for key, val in ra.items():
        assert isinstance(val, list), f"{key} should be a list"
