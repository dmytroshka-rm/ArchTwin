from __future__ import annotations

"""
tests/integration/test_graph_e2e.py
====================================
End-to-end tests for the compiled ISA-CAD LangGraph pipeline.

All nodes are replaced with lightweight stubs so the tests are fast,
deterministic, and independent of external stores.  Each stub returns the
minimum state needed to drive downstream nodes correctly.

Three scenarios are covered:
    A. Happy path  — all reviewers PASS, score > 0.70 → APPROVED
    B. Blocked     — security reviewer FAILs → is_blocked=True, BLOCKED
    C. Candidate   — cost reviewer WARNING, score < 0.70 → CANDIDATE_FOR_REVIEW
"""

import pytest

from isa_cad.agent.graph import build_graph
from isa_cad.agent.graph_state import AgentState
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.core.models.calibration import CalibrationResult
from isa_cad.core.models.enums import (
    ComponentTier,
    OptimizationGoal,
    ProposalStatus,
    ReviewerStatus,
    ReviewerType,
    VetoGateResult,
    VetoGateType,
)
from isa_cad.core.models.proposal import DesignProposal, NonLinearScoring, RequiredActions
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet
from isa_cad.core.freshness_engine import FreshnessReport
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
)


# ── Stub builders ──────────────────────────────────────────────────────────────

def _graph() -> ComponentGraph:
    return ComponentGraph(
        nodes=[
            ComponentNode(id="api",  label="API Gateway",  tier="standard"),
            ComponentNode(id="svc",  label="Auth Service", tier="standard"),
            ComponentNode(id="db",   label="User DB",      tier="tier_1"),
        ],
        edges=[
            ComponentEdge(source_id="api", target_id="svc"),
            ComponentEdge(source_id="svc", target_id="db"),
        ],
    )


def _cost_ok() -> CostReviewerOutput:
    return CostReviewerOutput(
        reviewer=ReviewerType.COST,
        status=ReviewerStatus.PASS,
        score=0.85,
        confidence=0.90,
        recommendation="Cost within budget.",
    )


def _cost_warn() -> CostReviewerOutput:
    return CostReviewerOutput(
        reviewer=ReviewerType.COST,
        status=ReviewerStatus.WARNING,
        score=0.55,
        confidence=0.70,
        recommendation="Cost increase detected.",
    )


def _perf_ok() -> PerformanceReviewerOutput:
    return PerformanceReviewerOutput(
        reviewer=ReviewerType.PERFORMANCE,
        status=ReviewerStatus.PASS,
        score=0.80,
        confidence=0.85,
        recommendation="Latency within SLO.",
    )


def _sec_ok() -> SecurityReviewerOutput:
    return SecurityReviewerOutput(
        reviewer=ReviewerType.SECURITY,
        status=ReviewerStatus.PASS,
        score=0.90,
        confidence=0.92,
        pii_flow_status="pass",
        compliance_status="pass",
        recommendation="No security issues.",
    )


def _sec_fail() -> SecurityReviewerOutput:
    return SecurityReviewerOutput(
        reviewer=ReviewerType.SECURITY,
        status=ReviewerStatus.FAIL,
        score=0.20,
        confidence=0.95,
        trust_boundary_violations=["svc→db missing auth layer"],
        pii_flow_status="fail",
        compliance_status="fail",
        recommendation="Critical security violations found.",
    )


def _veto_passed(gate_type: VetoGateType) -> VetoGate:
    return VetoGate(gate_type=gate_type, result=VetoGateResult.PASSED,
                    reason="passed")


def _veto_set_all_passed() -> VetoGateSet:
    return VetoGateSet(
        security_gate=_veto_passed(VetoGateType.SECURITY),
        reliability_gate=_veto_passed(VetoGateType.RELIABILITY),
        compliance_gate=_veto_passed(VetoGateType.COMPLIANCE),
        fidelity_gate=_veto_passed(VetoGateType.FIDELITY),
    )


def _proposal(score: float, *, blocked: bool = False) -> DesignProposal:
    veto_set = _veto_set_all_passed()
    if blocked:
        veto_set.security_gate = VetoGate(
            gate_type=VetoGateType.SECURITY,
            result=VetoGateResult.BLOCKED,
            reason="security fail",
            required_action="fix",
        )
    status = (
        ProposalStatus.BLOCKED if blocked
        else ProposalStatus.APPROVED if score >= 0.70
        else ProposalStatus.CANDIDATE_FOR_REVIEW
    )
    scoring = NonLinearScoring(
        recommendation_score=score,
        veto_gates=veto_set,
    )
    return DesignProposal(
        id="p-e2e",
        title="E2E Test Proposal",
        status=status,
        optimization_goal=OptimizationGoal.BALANCED,
        baseline_ref="arch.prod",
        scoring=scoring,
    )


def _blast() -> BlastRadiusOutput:
    return BlastRadiusOutput(
        source_component_id="api",
        max_traversal_depth=3,
        impacted_stable_components=[],
        summary="no high-risk components",
    )


def _calibration_output() -> CalibrationLoopOutput:
    out = CalibrationLoopOutput(result=CalibrationResult(), summary="ok")
    out.human_review_required = False
    return out


def _freshness() -> FreshnessReport:
    return FreshnessReport(sources=[])


def _session() -> CanvasSessionState:
    return CanvasSessionState(session_id="s-e2e", baseline_ref="arch.prod")


# ── Stub node factories ────────────────────────────────────────────────────────

class _ContextStub:
    """Returns a minimal context state that all downstream nodes can consume."""

    def __call__(self, state: AgentState) -> AgentState:
        return {
            **state,
            "canvas_session":      _session(),
            "resolved_graph":      _graph(),
            "freshness_report":    _freshness(),
            "calibration_result":  CalibrationResult(),
            "context_ready":       True,
            "context_errors":      [],
        }


class _DeltaStub:
    def __call__(self, state: AgentState) -> AgentState:
        return {
            **state,
            "design_delta":        {"added": [], "removed": [], "modified": ["api"]},
            "source_component_id": "api",
        }


class _ReviewerStub:
    def __init__(
        self,
        cost: CostReviewerOutput,
        perf: PerformanceReviewerOutput,
        sec: SecurityReviewerOutput,
    ) -> None:
        self._cost = cost
        self._perf = perf
        self._sec = sec

    def __call__(self, state: AgentState) -> AgentState:
        from isa_cad.agent.reviewers.orchestrator import (
            _aggregate_status,
            _collect_block_reasons,
            _combined_confidence,
            _reviewer_summary,
        )
        overall    = _aggregate_status(self._cost, self._perf, self._sec)
        reasons    = _collect_block_reasons(self._cost, self._perf, self._sec)
        confidence = _combined_confidence(self._cost, self._perf, self._sec)
        summary    = _reviewer_summary(self._cost, self._perf, self._sec,
                                       overall, confidence)
        from isa_cad.core.models.enums import ReviewerStatus
        return {
            **state,
            "cost_review":        self._cost,
            "performance_review": self._perf,
            "security_review":    self._sec,
            "reviewer_summary":   summary,
            "is_blocked":         overall == ReviewerStatus.FAIL,
            "block_reasons":      reasons,
        }


class _VetoStub:
    """Injects pre-built veto gates directly from a VetoGateSet."""

    def __init__(self, gate_set: VetoGateSet) -> None:
        self._gs = gate_set

    def security_node(self):
        gs = self._gs
        class _N:
            def __call__(self, state):
                return {"security_gate": gs.security_gate}
        return _N()

    def reliability_node(self):
        gs = self._gs
        class _N:
            def __call__(self, state):
                return {"reliability_gate": gs.reliability_gate}
        return _N()

    def compliance_node(self):
        gs = self._gs
        class _N:
            def __call__(self, state):
                return {"compliance_gate": gs.compliance_gate}
        return _N()

    def fidelity_node(self):
        gs = self._gs
        class _N:
            def __call__(self, state):
                return {"fidelity_gate": gs.fidelity_gate}
        return _N()


class _TradeoffStub:
    def __init__(self, proposal: DesignProposal) -> None:
        self._proposal = proposal

    def __call__(self, state: AgentState) -> AgentState:
        return {**state, "proposal": self._proposal}


class _BlastStub:
    def __call__(self, state: AgentState) -> AgentState:
        return {**state, "blast_radius": _blast()}


class _CalibrationStub:
    def __call__(self, state: AgentState) -> AgentState:
        return {**state, "calibration_loop_output": _calibration_output()}


class _PersistenceStub:
    def __call__(self, state: AgentState) -> AgentState:
        return {**state, "checkpoint_required": False}


# ── Graph builder helper ───────────────────────────────────────────────────────

def _build(
    cost: CostReviewerOutput,
    perf: PerformanceReviewerOutput,
    sec: SecurityReviewerOutput,
    proposal: DesignProposal,
):
    gate_set = _veto_set_all_passed()
    if proposal.is_blocked:
        gate_set.security_gate = proposal.scoring.veto_gates.security_gate

    vs = _VetoStub(gate_set)

    return build_graph(
        context_freshness_node   = _ContextStub(),
        build_delta_node         = _DeltaStub(),
        parallel_reviewer_node   = _ReviewerStub(cost, perf, sec),
        security_veto_node       = vs.security_node(),
        reliability_veto_node    = vs.reliability_node(),
        compliance_veto_node     = vs.compliance_node(),
        fidelity_veto_node       = vs.fidelity_node(),
        tradeoff_veto_node       = _TradeoffStub(proposal),
        blast_radius_node        = _BlastStub(),
        calibration_node         = _CalibrationStub(),
        persistence_node         = _PersistenceStub(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Scenario A: Happy path — all pass → APPROVED
# ══════════════════════════════════════════════════════════════════════════════

class TestHappyPath:
    @pytest.fixture(scope="class")
    def final_state(self) -> AgentState:
        proposal = _proposal(score=0.82)
        graph    = _build(_cost_ok(), _perf_ok(), _sec_ok(), proposal)
        return graph.invoke({
            "session_id":        "s-e2e",
            "proposal_id":       "p-e2e",
            "baseline_ref":      "arch.prod",
            "optimization_goal": OptimizationGoal.BALANCED,
        })

    def test_pipeline_returns_dict(self, final_state):
        assert isinstance(final_state, dict)

    def test_final_output_present(self, final_state):
        assert "final_output" in final_state
        assert isinstance(final_state["final_output"], dict)

    def test_decision_approved(self, final_state):
        assert final_state["final_output"]["decision"] == ProposalStatus.APPROVED.value

    def test_not_blocked(self, final_state):
        assert final_state.get("is_blocked") is False or "is_blocked" not in final_state

    def test_human_review_not_required(self, final_state):
        hrr = final_state.get("human_review_request", {})
        assert hrr.get("required") is False

    def test_recommendations_present(self, final_state):
        # May be empty if no signals fire, but key must exist
        assert "recommendations" in final_state

    def test_isa_yaml_patch_present(self, final_state):
        assert "isa_yaml_patch" in final_state

    def test_proposal_status_approved(self, final_state):
        proposal: DesignProposal = final_state["proposal"]
        assert proposal.status == ProposalStatus.APPROVED

    def test_all_nodes_ran(self, final_state):
        # Check that key outputs from every major node are present
        for key in (
            "canvas_session", "resolved_graph", "freshness_report",
            "design_delta", "cost_review", "performance_review",
            "security_review", "proposal", "blast_radius",
            "calibration_loop_output", "final_output",
            "human_review_request",
        ):
            assert key in final_state, f"missing key: {key}"


# ══════════════════════════════════════════════════════════════════════════════
# Scenario B: Security FAIL → BLOCKED + human review critical
# ══════════════════════════════════════════════════════════════════════════════

class TestBlockedScenario:
    @pytest.fixture(scope="class")
    def final_state(self) -> AgentState:
        proposal = _proposal(score=0.10, blocked=True)
        graph    = _build(_cost_ok(), _perf_ok(), _sec_fail(), proposal)
        return graph.invoke({
            "session_id":        "s-blocked",
            "proposal_id":       "p-blocked",
            "baseline_ref":      "arch.prod",
            "optimization_goal": OptimizationGoal.MAX_RELIABILITY,
            "is_blocked":        True,
            "block_reasons":     ["[security] Critical security violations found."],
        })

    def test_decision_blocked(self, final_state):
        assert final_state["final_output"]["decision"] == ProposalStatus.BLOCKED.value

    def test_is_blocked_true(self, final_state):
        assert final_state.get("is_blocked") is True

    def test_human_review_required(self, final_state):
        assert final_state["human_review_request"]["required"] is True

    def test_human_review_critical(self, final_state):
        assert final_state["human_review_request"]["escalation_level"] == "critical"

    def test_block_reasons_present(self, final_state):
        assert final_state.get("block_reasons")

    def test_proposal_status_blocked(self, final_state):
        assert final_state["proposal"].status == ProposalStatus.BLOCKED

    def test_accept_risk_not_in_options_for_critical(self, final_state):
        from isa_cad.core.models.enums import HumanDecision
        options = final_state["human_review_request"]["options"]
        assert HumanDecision.ACCEPT_RISK_WITH_ADR.value not in options

    def test_checkpoint_required(self, final_state):
        assert final_state.get("checkpoint_required") is True


# ══════════════════════════════════════════════════════════════════════════════
# Scenario C: Low score → CANDIDATE_FOR_REVIEW, warning level human review
# ══════════════════════════════════════════════════════════════════════════════

class TestCandidateScenario:
    @pytest.fixture(scope="class")
    def final_state(self) -> AgentState:
        proposal = _proposal(score=0.55)  # below 0.70 threshold
        graph    = _build(_cost_warn(), _perf_ok(), _sec_ok(), proposal)
        return graph.invoke({
            "session_id":        "s-candidate",
            "proposal_id":       "p-candidate",
            "baseline_ref":      "arch.prod",
            "optimization_goal": OptimizationGoal.COST_EFFICIENCY,
        })

    def test_decision_candidate(self, final_state):
        assert final_state["final_output"]["decision"] == ProposalStatus.CANDIDATE_FOR_REVIEW.value

    def test_human_review_required(self, final_state):
        assert final_state["human_review_request"]["required"] is True

    def test_proposal_status_candidate(self, final_state):
        assert final_state["proposal"].status == ProposalStatus.CANDIDATE_FOR_REVIEW

    def test_not_blocked(self, final_state):
        # not hard-blocked even if review required
        fo = final_state["final_output"]
        assert fo.get("decision") != ProposalStatus.BLOCKED.value


# ══════════════════════════════════════════════════════════════════════════════
# Graph structure tests (independent of scenario)
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphStructure:

    def test_graph_compiles(self):
        g = build_graph()
        assert g is not None

    def test_expected_nodes_present(self):
        g = build_graph()
        expected = {
            "context_freshness", "build_design_delta", "parallel_reviewer",
            "security_veto", "reliability_veto", "compliance_veto", "fidelity_veto",
            "tradeoff_veto", "blast_radius", "calibration", "state_persistence",
            "reflect_decide", "required_actions", "isa_yaml_patch",
            "sandbox_recommendation", "human_review_gate", "human_decision_processor",
        }
        assert expected.issubset(set(g.nodes))

    def test_node_count(self):
        g = build_graph()
        # 17 named nodes + __start__
        assert len(list(g.nodes)) == 18

    def test_graph_is_runnable(self):
        g = build_graph()
        assert hasattr(g, "invoke") and callable(g.invoke)
