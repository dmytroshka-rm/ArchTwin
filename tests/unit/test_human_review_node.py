from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.human_review import (
    HumanDecisionProcessorNode,
    HumanReviewGateNode,
    _HIGH_RISK_THRESHOLD,
)
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput
from isa_cad.core.models.blast_radius import BlastRadiusOutput, ImpactedComponent
from isa_cad.core.models.calibration import CalibrationResult
from isa_cad.core.models.enums import (
    ComponentTier,
    HumanDecision,
    OptimizationGoal,
    ProposalStatus,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.human_review import HumanReviewRequest
from isa_cad.core.models.proposal import DesignProposal, NonLinearScoring, RequiredActions
from isa_cad.core.models.veto import VetoGate
from isa_cad.state.canvas_state import CanvasSessionState

gate_node = HumanReviewGateNode()
decision_node = HumanDecisionProcessorNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def degraded(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.DEGRADED, reason="warn")


def blocked_gate(t: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=t, result=VetoGateResult.BLOCKED, reason="fail",
                    required_action="fix")


def make_proposal(status: ProposalStatus = ProposalStatus.CANDIDATE_FOR_REVIEW) -> DesignProposal:
    return DesignProposal(
        id="p-test", title="Test", status=status,
        optimization_goal=OptimizationGoal.BALANCED,
        baseline_ref="arch.prod",
        scoring=NonLinearScoring(),
    )


def make_cal(human_review: bool) -> CalibrationLoopOutput:
    out = CalibrationLoopOutput(result=CalibrationResult(), summary="")
    out.human_review_required = human_review
    return out


def blast(high_risk: int) -> BlastRadiusOutput:
    comps = [
        ImpactedComponent(id=f"db-{i}", tier=ComponentTier.TIER_1,
                          distance=1, criticality_multiplier=2.0,
                          impact_score=2.0, risk="io")
        for i in range(high_risk)
    ]
    return BlastRadiusOutput(source_component_id="api", max_traversal_depth=3,
                             impacted_stable_components=comps, summary="")


def make_session() -> CanvasSessionState:
    return CanvasSessionState(session_id="s-1", baseline_ref="arch.prod")


# ══════════════════════════════════════════════════════════════════════════════
# HumanReviewGateNode
# ══════════════════════════════════════════════════════════════════════════════

class TestHumanReviewGateNode:

    # ── Output contract ───────────────────────────────────────────────────────

    def test_key_always_present(self):
        result = gate_node({})
        assert "human_review_request" in result

    def test_empty_state_not_required(self):
        result = gate_node({})
        assert result["human_review_request"]["required"] is False

    def test_state_passthrough(self):
        result = gate_node({"session_id": "s-1"})
        assert result["session_id"] == "s-1"

    # ── No escalation ─────────────────────────────────────────────────────────

    def test_no_signals_not_required(self):
        state: AgentState = {
            "is_blocked": False,
            "final_output": {"decision": "approved"},
        }
        result = gate_node(state)
        assert result["human_review_request"]["required"] is False

    def test_not_required_no_checkpoint_set(self):
        result = gate_node({"is_blocked": False})
        assert result.get("checkpoint_required", False) is False

    # ── BLOCKED escalation ────────────────────────────────────────────────────

    def test_is_blocked_sets_required(self):
        state: AgentState = {"is_blocked": True, "block_reasons": ["[security] fail"]}
        result = gate_node(state)
        assert result["human_review_request"]["required"] is True

    def test_is_blocked_level_critical(self):
        state: AgentState = {"is_blocked": True}
        result = gate_node(state)
        assert result["human_review_request"]["escalation_level"] == "critical"

    def test_is_blocked_sets_checkpoint_required(self):
        state: AgentState = {"is_blocked": True}
        result = gate_node(state)
        assert result["checkpoint_required"] is True

    def test_blocked_reasons_included(self):
        state: AgentState = {
            "is_blocked": True,
            "block_reasons": ["[security_gate] violation"],
        }
        result = gate_node(state)
        reasons = result["human_review_request"]["reasons"]
        assert any("[security_gate]" in r for r in reasons)

    # ── Calibration human_review_required ─────────────────────────────────────

    def test_cal_human_review_sets_required(self):
        state: AgentState = {"calibration_loop_output": make_cal(human_review=True)}
        result = gate_node(state)
        assert result["human_review_request"]["required"] is True

    def test_cal_human_review_level_warning(self):
        state: AgentState = {"calibration_loop_output": make_cal(human_review=True)}
        result = gate_node(state)
        assert result["human_review_request"]["escalation_level"] == "warning"

    def test_cal_human_review_not_triggered_when_false(self):
        state: AgentState = {"calibration_loop_output": make_cal(human_review=False)}
        result = gate_node(state)
        assert result["human_review_request"]["required"] is False

    # ── Blast radius threshold ────────────────────────────────────────────────

    def test_high_risk_at_threshold_sets_required(self):
        state: AgentState = {"blast_radius": blast(_HIGH_RISK_THRESHOLD)}
        result = gate_node(state)
        assert result["human_review_request"]["required"] is True

    def test_high_risk_below_threshold_not_required(self):
        state: AgentState = {"blast_radius": blast(_HIGH_RISK_THRESHOLD - 1)}
        result = gate_node(state)
        assert result["human_review_request"]["required"] is False

    def test_high_risk_level_warning(self):
        state: AgentState = {"blast_radius": blast(_HIGH_RISK_THRESHOLD)}
        result = gate_node(state)
        assert result["human_review_request"]["escalation_level"] == "warning"

    # ── Fidelity gate → REQUEST_REFRESH option ────────────────────────────────

    def test_fidelity_degraded_adds_refresh_option(self):
        state: AgentState = {
            "fidelity_gate": degraded(VetoGateType.FIDELITY),
            "is_blocked": True,  # ensure required=True
        }
        result = gate_node(state)
        options = result["human_review_request"]["options"]
        assert HumanDecision.REQUEST_REFRESH.value in options

    def test_fidelity_passed_no_refresh_option(self):
        state: AgentState = {
            "fidelity_gate": VetoGate(gate_type=VetoGateType.FIDELITY,
                                       result=VetoGateResult.PASSED),
            "is_blocked": True,
        }
        result = gate_node(state)
        options = result["human_review_request"]["options"]
        assert HumanDecision.REQUEST_REFRESH.value not in options

    def test_fidelity_degraded_adds_deadline_hint(self):
        state: AgentState = {
            "fidelity_gate": degraded(VetoGateType.FIDELITY),
            "is_blocked": True,
        }
        result = gate_node(state)
        assert result["human_review_request"]["deadline_hint"] != ""

    # ── ACCEPT_RISK_WITH_ADR option ───────────────────────────────────────────

    def test_warning_adds_accept_risk_option(self):
        state: AgentState = {"calibration_loop_output": make_cal(human_review=True)}
        result = gate_node(state)
        options = result["human_review_request"]["options"]
        assert HumanDecision.ACCEPT_RISK_WITH_ADR.value in options

    def test_critical_does_not_add_accept_risk_option(self):
        state: AgentState = {"is_blocked": True}
        result = gate_node(state)
        options = result["human_review_request"]["options"]
        assert HumanDecision.ACCEPT_RISK_WITH_ADR.value not in options

    # ── CANDIDATE_FOR_REVIEW signal ───────────────────────────────────────────

    def test_candidate_decision_adds_reason(self):
        state: AgentState = {
            "is_blocked": False,
            "final_output": {"decision": "candidate_for_review"},
        }
        result = gate_node(state)
        req = result["human_review_request"]
        assert req["required"] is True
        assert req["reasons"]


# ══════════════════════════════════════════════════════════════════════════════
# HumanDecisionProcessorNode
# ══════════════════════════════════════════════════════════════════════════════

class TestHumanDecisionProcessorNode:

    # ── No-op when absent ─────────────────────────────────────────────────────

    def test_no_decision_no_change(self):
        state: AgentState = {"proposal": make_proposal(), "session_id": "s-1"}
        result = decision_node(state)
        assert result["session_id"] == "s-1"
        assert result["proposal"].status == ProposalStatus.CANDIDATE_FOR_REVIEW

    # ── APPROVE_SANDBOX_LAYER ─────────────────────────────────────────────────

    def test_approve_sets_proposal_approved(self):
        proposal = make_proposal(ProposalStatus.CANDIDATE_FOR_REVIEW)
        state: AgentState = {
            "proposal": proposal,
            "human_decision": HumanDecision.APPROVE_SANDBOX_LAYER,
        }
        decision_node(state)
        assert proposal.status == ProposalStatus.APPROVED

    def test_approve_updates_final_output(self):
        state: AgentState = {
            "proposal": make_proposal(),
            "human_decision": HumanDecision.APPROVE_SANDBOX_LAYER,
            "final_output": {"decision": "candidate_for_review"},
        }
        result = decision_node(state)
        assert result["final_output"]["decision"] == "approved"

    # ── BLOCK_PROPOSAL ────────────────────────────────────────────────────────

    def test_block_sets_proposal_blocked(self):
        proposal = make_proposal()
        state: AgentState = {
            "proposal": proposal,
            "human_decision": HumanDecision.BLOCK_PROPOSAL,
        }
        decision_node(state)
        assert proposal.status == ProposalStatus.BLOCKED

    def test_block_sets_is_blocked_true(self):
        state: AgentState = {
            "proposal": make_proposal(),
            "human_decision": HumanDecision.BLOCK_PROPOSAL,
            "is_blocked": False,
        }
        result = decision_node(state)
        assert result["is_blocked"] is True

    def test_block_appends_block_reason(self):
        state: AgentState = {
            "proposal": make_proposal(),
            "human_decision": HumanDecision.BLOCK_PROPOSAL,
            "block_reasons": [],
        }
        result = decision_node(state)
        assert any("[human_decision]" in r for r in result["block_reasons"])

    def test_block_reason_not_duplicated(self):
        existing = ["[human_decision] Proposal blocked by human reviewer."]
        state: AgentState = {
            "proposal": make_proposal(),
            "human_decision": HumanDecision.BLOCK_PROPOSAL,
            "block_reasons": existing,
        }
        result = decision_node(state)
        count = sum(1 for r in result["block_reasons"] if "[human_decision]" in r)
        assert count == 1

    # ── REQUEST_REFRESH ───────────────────────────────────────────────────────

    def test_request_refresh_marks_session_stale(self):
        sess = make_session()
        assert not sess.observed_graph_stale
        state: AgentState = {
            "canvas_session": sess,
            "human_decision": HumanDecision.REQUEST_REFRESH,
        }
        decision_node(state)
        assert sess.observed_graph_stale is True

    def test_request_refresh_sets_checkpoint_required(self):
        state: AgentState = {
            "human_decision": HumanDecision.REQUEST_REFRESH,
        }
        result = decision_node(state)
        assert result["checkpoint_required"] is True

    def test_request_refresh_no_session_no_crash(self):
        state: AgentState = {"human_decision": HumanDecision.REQUEST_REFRESH}
        result = decision_node(state)
        assert result["checkpoint_required"] is True

    # ── ACCEPT_RISK_WITH_ADR ──────────────────────────────────────────────────

    def test_accept_risk_sets_approved(self):
        proposal = make_proposal()
        state: AgentState = {
            "proposal": proposal,
            "human_decision": HumanDecision.ACCEPT_RISK_WITH_ADR,
        }
        decision_node(state)
        assert proposal.status == ProposalStatus.APPROVED

    def test_accept_risk_adds_adr_note(self):
        proposal = make_proposal()
        state: AgentState = {
            "proposal": proposal,
            "human_decision": HumanDecision.ACCEPT_RISK_WITH_ADR,
        }
        decision_node(state)
        assert any("ADR" in a for a in proposal.required_actions.architect)

    def test_accept_risk_sets_adr_required_in_final_output(self):
        state: AgentState = {
            "proposal": make_proposal(),
            "human_decision": HumanDecision.ACCEPT_RISK_WITH_ADR,
            "final_output": {"decision": "candidate_for_review"},
        }
        result = decision_node(state)
        assert result["final_output"].get("adr_required") is True

    # ── MODIFY_GOAL ───────────────────────────────────────────────────────────

    def test_modify_goal_sets_needs_rerun(self):
        state: AgentState = {"human_decision": HumanDecision.MODIFY_GOAL}
        result = decision_node(state)
        assert result["needs_rerun"] is True

    def test_modify_goal_updates_final_output(self):
        state: AgentState = {
            "human_decision": HumanDecision.MODIFY_GOAL,
            "final_output": {"decision": "candidate_for_review"},
        }
        result = decision_node(state)
        assert result["final_output"]["needs_rerun"] is True
        assert "rerun_reason" in result["final_output"]

    # ── State passthrough ─────────────────────────────────────────────────────

    def test_passthrough_with_decision(self):
        state: AgentState = {
            "proposal": make_proposal(),
            "human_decision": HumanDecision.APPROVE_SANDBOX_LAYER,
            "session_id": "sess-human",
        }
        result = decision_node(state)
        assert result["session_id"] == "sess-human"
