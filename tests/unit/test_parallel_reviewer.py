from __future__ import annotations

import threading
import time

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.reviewers.cost import CostReviewerNode
from isa_cad.agent.reviewers.orchestrator import (
    ParallelReviewerNode,
    _aggregate_status,
    _collect_block_reasons,
    _combined_confidence,
)
from isa_cad.agent.reviewers.performance import PerformanceReviewerNode
from isa_cad.agent.reviewers.security import SecurityReviewerNode
from isa_cad.core.models.enums import OptimizationGoal, ReviewerStatus
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)

orchestrator = ParallelReviewerNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_reviewer_output(
    cls,
    status: ReviewerStatus = ReviewerStatus.PASS,
    score: float = 0.8,
    confidence: float = 0.7,
) -> CostReviewerOutput | PerformanceReviewerOutput | SecurityReviewerOutput:
    return cls(status=status, score=score, confidence=confidence,
               recommendation="ok")


def make_session_and_graph(
    add_violation: bool = False,
    add_cost_hike: bool = False,
) -> tuple[CanvasSessionState, ComponentGraph]:
    """
    Build a simple baseline + (optionally) a proposed graph that triggers
    specific reviewer signals.
    """
    baseline = ComponentGraph(
        nodes=[
            ComponentNode(id="api",    label="API",    tier="standard",  component_type="service"),
            ComponentNode(id="db",     label="DB",     tier="tier_1",    component_type="database"),
        ],
        edges=[ComponentEdge(source_id="api", target_id="db")],
    )

    extra_nodes = list(baseline.nodes)
    extra_edges = list(baseline.edges)

    if add_violation:
        # Add a gateway that bypasses the service layer → trust violation
        gw = ComponentNode(id="gw", label="GW", tier="standard", component_type="gateway")
        extra_nodes.append(gw)
        extra_edges.append(ComponentEdge(source_id="gw", target_id="db"))

    if add_cost_hike:
        # Add 15 databases → cost > 25% above baseline → FAIL
        for i in range(15):
            extra_nodes.append(
                ComponentNode(id=f"db_extra_{i}", label=f"DB{i}",
                              tier="tier_1", component_type="database")
            )

    proposed = ComponentGraph(nodes=extra_nodes, edges=extra_edges)
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = baseline
    return session, proposed


def run(
    session: CanvasSessionState,
    resolved: ComponentGraph,
    goal: OptimizationGoal = OptimizationGoal.BALANCED,
) -> dict:
    state: AgentState = {
        "canvas_session": session,
        "resolved_graph": resolved,
        "optimization_goal": goal,
    }
    return orchestrator(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_all_three_reviewers_present():
    session, resolved = make_session_and_graph()
    result = run(session, resolved)

    assert "cost_review" in result
    assert "performance_review" in result
    assert "security_review" in result


def test_reviewer_summary_keys():
    session, resolved = make_session_and_graph()
    result = run(session, resolved)
    summary = result["reviewer_summary"]

    assert "overall_status" in summary
    assert "combined_confidence" in summary
    assert "reviewers" in summary
    assert set(summary["reviewers"].keys()) == {"cost", "performance", "security"}
    assert "block_sources" in summary


def test_is_blocked_and_block_reasons_present():
    session, resolved = make_session_and_graph()
    result = run(session, resolved)
    assert "is_blocked" in result
    assert "block_reasons" in result
    assert isinstance(result["block_reasons"], list)


def test_no_session_returns_unknown_all():
    """All reviewers gracefully degrade with empty state."""
    result = orchestrator({})
    assert result["cost_review"].status == ReviewerStatus.UNKNOWN
    assert result["performance_review"].status == ReviewerStatus.UNKNOWN
    assert result["security_review"].status == ReviewerStatus.UNKNOWN
    assert result["is_blocked"] is False   # UNKNOWN is not FAIL


# ── Aggregation logic ─────────────────────────────────────────────────────────

def test_aggregate_all_pass_gives_pass():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.PASS)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.PASS)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.PASS)
    assert _aggregate_status(c, p, s) == ReviewerStatus.PASS


def test_aggregate_one_fail_gives_fail():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.FAIL)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.PASS)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.PASS)
    assert _aggregate_status(c, p, s) == ReviewerStatus.FAIL


def test_aggregate_warning_no_fail_gives_warning():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.WARNING)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.PASS)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.PASS)
    assert _aggregate_status(c, p, s) == ReviewerStatus.WARNING


def test_aggregate_fail_beats_warning():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.FAIL)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.WARNING)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.PASS)
    assert _aggregate_status(c, p, s) == ReviewerStatus.FAIL


def test_aggregate_all_unknown_gives_unknown():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.UNKNOWN)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.UNKNOWN)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.UNKNOWN)
    assert _aggregate_status(c, p, s) == ReviewerStatus.UNKNOWN


# ── Block reasons ─────────────────────────────────────────────────────────────

def test_no_fail_no_block_reasons():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.PASS)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.PASS)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.PASS)
    assert _collect_block_reasons(c, p, s) == []


def test_cost_fail_produces_block_reason():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.FAIL)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.PASS)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.PASS)
    reasons = _collect_block_reasons(c, p, s)
    assert any("[cost]" in r for r in reasons)


def test_security_violations_added_to_block_reasons():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.PASS)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.PASS)
    s = SecurityReviewerOutput(
        status=ReviewerStatus.FAIL,
        score=0.2,
        confidence=0.6,
        recommendation="Security FAIL",
        trust_boundary_violations=["gw → db: violation"],
    )
    reasons = _collect_block_reasons(c, p, s)
    assert any("[security:trust_violation]" in r for r in reasons)


def test_multiple_fail_all_block_reasons_present():
    c = _make_reviewer_output(CostReviewerOutput, ReviewerStatus.FAIL)
    p = _make_reviewer_output(PerformanceReviewerOutput, ReviewerStatus.FAIL)
    s = _make_reviewer_output(SecurityReviewerOutput, ReviewerStatus.FAIL)
    reasons = _collect_block_reasons(c, p, s)
    assert any("[cost]" in r for r in reasons)
    assert any("[performance]" in r for r in reasons)
    assert any("[security]" in r for r in reasons)


# ── Combined confidence ───────────────────────────────────────────────────────

def test_combined_confidence_is_minimum():
    c = _make_reviewer_output(CostReviewerOutput, confidence=0.9)
    p = _make_reviewer_output(PerformanceReviewerOutput, confidence=0.6)
    s = _make_reviewer_output(SecurityReviewerOutput, confidence=0.75)
    assert _combined_confidence(c, p, s) == pytest.approx(0.6)


# ── is_blocked integration ────────────────────────────────────────────────────

def test_security_violation_sets_is_blocked():
    """Topology with trust boundary violation → security FAIL → is_blocked."""
    session, resolved = make_session_and_graph(add_violation=True)
    result = run(session, resolved)
    assert result["security_review"].status == ReviewerStatus.FAIL
    assert result["is_blocked"] is True
    assert len(result["block_reasons"]) > 0


def test_cost_hike_sets_is_blocked():
    """Large cost increase → cost FAIL → is_blocked."""
    session, resolved = make_session_and_graph(add_cost_hike=True)
    result = run(session, resolved)
    assert result["cost_review"].status == ReviewerStatus.FAIL
    assert result["is_blocked"] is True


def test_clean_graph_not_blocked():
    """Minimal clean graph → no failures → is_blocked=False."""
    g = ComponentGraph(
        nodes=[ComponentNode(id="svc", label="Svc", tier="standard", component_type="service")],
    )
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = g
    result = run(session, g)
    assert result["is_blocked"] is False


# ── Block sources in summary ──────────────────────────────────────────────────

def test_block_sources_lists_fail_reviewers():
    session, resolved = make_session_and_graph(add_violation=True, add_cost_hike=True)
    result = run(session, resolved)
    sources = result["reviewer_summary"]["block_sources"]
    assert "security" in sources
    assert "cost" in sources


def test_no_block_sources_when_all_pass():
    g = ComponentGraph(
        nodes=[ComponentNode(id="svc", label="Svc", tier="standard", component_type="service")],
    )
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = g
    result = run(session, g)
    assert result["reviewer_summary"]["block_sources"] == []


# ── Parallelism ───────────────────────────────────────────────────────────────

def test_results_consistent_across_runs():
    """Parallel runs should produce deterministic outputs."""
    session, resolved = make_session_and_graph()
    r1 = run(session, resolved)
    r2 = run(session, resolved)
    assert r1["cost_review"].status == r2["cost_review"].status
    assert r1["performance_review"].score == r2["performance_review"].score
    assert r1["security_review"].compliance_status == r2["security_review"].compliance_status


def test_threads_ran_independently():
    """
    Verify the three reviewers ran (approximately) in parallel by
    injecting a slow no-op reviewer and checking wall-clock time.
    """
    call_order: list[str] = []
    lock = threading.Lock()

    class SlowCost(CostReviewerNode):
        def __call__(self, state):
            time.sleep(0.05)
            with lock:
                call_order.append("cost")
            return super().__call__(state)

    class SlowPerf(PerformanceReviewerNode):
        def __call__(self, state):
            time.sleep(0.05)
            with lock:
                call_order.append("perf")
            return super().__call__(state)

    class SlowSec(SecurityReviewerNode):
        def __call__(self, state):
            time.sleep(0.05)
            with lock:
                call_order.append("sec")
            return super().__call__(state)

    node = ParallelReviewerNode(
        cost_node=SlowCost(),
        perf_node=SlowPerf(),
        sec_node=SlowSec(),
    )
    g = ComponentGraph(nodes=[
        ComponentNode(id="svc", label="Svc", tier="standard", component_type="service")
    ])
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = g

    start = time.perf_counter()
    node({"canvas_session": session, "resolved_graph": g})
    elapsed = time.perf_counter() - start

    # If sequential, 3 × 50ms = 150ms; parallel should be close to 50ms
    # We allow 120ms as a generous threshold for slow CI environments
    assert elapsed < 0.12, f"Reviewers appear to run sequentially: {elapsed:.3f}s"
    assert set(call_order) == {"cost", "perf", "sec"}


# ── Reviewer summary structure ────────────────────────────────────────────────

def test_summary_overall_status_matches_aggregate():
    session, resolved = make_session_and_graph(add_violation=True)
    result = run(session, resolved)
    summary = result["reviewer_summary"]
    assert summary["overall_status"] == result["security_review"].status.value


def test_summary_confidence_is_minimum_of_three():
    session, resolved = make_session_and_graph()
    result = run(session, resolved)
    summary = result["reviewer_summary"]
    min_conf = min(
        result["cost_review"].confidence,
        result["performance_review"].confidence,
        result["security_review"].confidence,
    )
    assert summary["combined_confidence"] == pytest.approx(min_conf)


def test_summary_per_reviewer_score_present():
    session, resolved = make_session_and_graph()
    result = run(session, resolved)
    reviewers = result["reviewer_summary"]["reviewers"]
    for key in ("cost", "performance", "security"):
        assert "score" in reviewers[key]
        assert "status" in reviewers[key]
        assert "recommendation" in reviewers[key]
