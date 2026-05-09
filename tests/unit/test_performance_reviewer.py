from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.reviewers.performance import (
    PerformanceReviewerNode,
    _DB_PRESSURE_EDGE_THRESHOLD,
    _QUEUE_PRESSURE_EDGE_THRESHOLD,
    _db_pressure_risk,
    _graph_p95_ms,
    _graph_throughput_rps,
    _queue_pressure_risk,
    _score_from_latency_delta_pct,
    _status_from_risks,
)
from isa_cad.core.models.enums import OptimizationGoal, ReviewerStatus
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)

reviewer = PerformanceReviewerNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_graph(
    *specs: tuple[str, str],  # (id, component_type)
    edges: list[tuple[str, str]] | None = None,
    tier: str = "standard",
) -> ComponentGraph:
    nodes = [
        ComponentNode(id=s[0], label=s[0], tier=tier, component_type=s[1])
        for s in specs
    ]
    edge_objs = [
        ComponentEdge(source_id=e[0], target_id=e[1])
        for e in (edges or [])
    ]
    return ComponentGraph(nodes=nodes, edges=edge_objs)


def make_session(baseline: ComponentGraph) -> CanvasSessionState:
    s = CanvasSessionState(session_id="s", baseline_ref="b")
    s.baseline_graph = baseline
    return s


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
    return reviewer(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_keys_present():
    g = make_graph(("api", "service"), ("db", "database"))
    s = make_session(g)
    result = run(s, g)
    out = result["performance_review"]

    assert out.p95_baseline_ms is not None
    assert out.p95_projected_ms is not None
    assert out.p99_baseline_ms is not None
    assert out.p99_projected_ms is not None
    assert out.throughput_rps is not None
    assert out.latency_delta is not None
    assert out.status in ReviewerStatus
    assert 0.0 <= out.score <= 1.0
    assert 0.0 <= out.confidence <= 1.0
    assert out.recommendation != ""


def test_no_session_returns_unknown():
    result = reviewer({})
    out = result["performance_review"]
    assert out.status == ReviewerStatus.UNKNOWN
    assert out.confidence == 0.0
    assert "canvas_session" in out.missing_inputs


# ── Latency math ──────────────────────────────────────────────────────────────

def test_p95_increases_when_node_added():
    baseline = make_graph(("api", "service"), ("db", "database"))
    extra = ComponentNode(id="cache", label="Cache", tier="standard", component_type="cache")
    proposed = ComponentGraph(nodes=baseline.nodes + [extra])
    s = make_session(baseline)
    result = run(s, proposed)
    out = result["performance_review"]
    assert out.p95_projected_ms > out.p95_baseline_ms


def test_p95_decreases_when_high_latency_node_removed():
    """Remove external node (50ms) → proposed P95 lower."""
    baseline = make_graph(("api", "service"), ("ext", "external"))
    proposed = make_graph(("api", "service"))
    s = make_session(baseline)
    result = run(s, proposed)
    out = result["performance_review"]
    assert out.p95_projected_ms < out.p95_baseline_ms
    assert "-" in out.latency_delta


def test_no_changes_pass_status():
    g = make_graph(("api", "service"), ("db", "database"))
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].status == ReviewerStatus.PASS


def test_latency_delta_string_format():
    g = make_graph(("api", "service"))
    s = make_session(g)
    result = run(s, g)
    delta = result["performance_review"].latency_delta
    assert "ms" in delta
    assert "%" in delta


# ── Score sensitivity ─────────────────────────────────────────────────────────

def test_latency_improvement_score_above_half():
    baseline = make_graph(("api", "service"), ("ext", "external"), ("ext2", "external"))
    proposed = make_graph(("api", "service"))
    s = make_session(baseline)
    result = run(s, proposed)
    assert result["performance_review"].score > 0.5


def test_max_reliability_amplifies_score():
    baseline = make_graph(("api", "service"), ("ext", "external"), ("ext2", "external"))
    proposed = make_graph(("api", "service"))
    s = make_session(baseline)
    r_balanced = run(s, proposed, goal=OptimizationGoal.BALANCED)
    r_rel      = run(s, proposed, goal=OptimizationGoal.MAX_RELIABILITY)
    assert r_rel["performance_review"].score >= r_balanced["performance_review"].score


def test_large_latency_increase_fail():
    """Add many high-latency external nodes → delta > 50% → FAIL."""
    baseline = make_graph(("api", "service"))
    extras = [
        ComponentNode(id=f"ext{i}", label=f"Ext{i}", tier="standard", component_type="external")
        for i in range(5)
    ]
    proposed = ComponentGraph(nodes=baseline.nodes + extras)
    s = make_session(baseline)
    result = run(s, proposed)
    out = result["performance_review"]
    assert out.status in (ReviewerStatus.FAIL, ReviewerStatus.WARNING)
    assert out.p95_projected_ms > out.p95_baseline_ms


# ── DB pressure ───────────────────────────────────────────────────────────────

def test_db_high_pressure_sets_fail():
    """Many services → single DB → high fan-in."""
    edges = [(f"svc{i}", "db") for i in range(_DB_PRESSURE_EDGE_THRESHOLD + 2)]
    nodes = [("db", "database")] + [(f"svc{i}", "service") for i in range(_DB_PRESSURE_EDGE_THRESHOLD + 2)]
    g = make_graph(*nodes, edges=edges)
    s = make_session(g)
    result = run(s, g)
    out = result["performance_review"]
    assert out.db_pressure_risk == "high"
    assert out.status == ReviewerStatus.FAIL
    assert any("database fan-in" in f.title.lower() for f in out.findings)


def test_db_medium_pressure():
    g = make_graph(
        ("db", "database"), ("svc1", "service"), ("svc2", "service"),
        edges=[("svc1", "db"), ("svc2", "db")],
    )
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].db_pressure_risk == "medium"


def test_no_db_low_pressure():
    g = make_graph(("api", "service"))
    assert _db_pressure_risk(g) == "low"


# ── Queue pressure ────────────────────────────────────────────────────────────

def test_queue_high_pressure_finding():
    edges = [(f"svc{i}", "q") for i in range(_QUEUE_PRESSURE_EDGE_THRESHOLD + 2)]
    nodes = [("q", "queue")] + [(f"svc{i}", "service") for i in range(_QUEUE_PRESSURE_EDGE_THRESHOLD + 2)]
    g = make_graph(*nodes, edges=edges)
    s = make_session(g)
    result = run(s, g)
    out = result["performance_review"]
    assert out.queue_pressure_risk == "high"
    assert any("queue" in f.title.lower() for f in out.findings)


def test_no_queue_low_pressure():
    g = make_graph(("api", "service"))
    assert _queue_pressure_risk(g) == "low"


# ── Cold-start risk ───────────────────────────────────────────────────────────

def test_cold_start_risk_for_lambda():
    g = make_graph(("fn", "lambda"), ("api", "service"))
    s = make_session(g)
    result = run(s, g)
    out = result["performance_review"]
    assert out.cold_start_risk == "high"
    assert any("cold" in f.title.lower() for f in out.findings)


def test_no_cold_start_risk_for_service():
    g = make_graph(("api", "service"), ("db", "database"))
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].cold_start_risk == "low"


# ── P99 > P95 ─────────────────────────────────────────────────────────────────

def test_p99_greater_than_p95():
    g = make_graph(("api", "service"), ("db", "database"))
    s = make_session(g)
    result = run(s, g)
    out = result["performance_review"]
    assert out.p99_baseline_ms >= out.p95_baseline_ms
    assert out.p99_projected_ms >= out.p95_projected_ms


# ── Throughput ────────────────────────────────────────────────────────────────

def test_throughput_limited_by_external():
    """External node (100 RPS) bounds the graph throughput."""
    g = make_graph(("api", "service"), ("ext", "external"))
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].throughput_rps == pytest.approx(100.0, abs=1)


def test_throughput_finding_for_low_rps():
    """Graph with only external nodes → finding about low throughput ceiling."""
    g = make_graph(("ext", "external"))
    s = make_session(g)
    result = run(s, g)
    titles = [f.title.lower() for f in result["performance_review"].findings]
    assert any("throughput" in t for t in titles)


# ── Observed metadata ─────────────────────────────────────────────────────────

def test_observed_p95_metadata_used():
    """Node with p95_latency_ms=2ms overrides heuristic (5ms for service)."""
    n = ComponentNode(
        id="fast-svc", label="Fast", tier="standard", component_type="service",
        metadata={"p95_latency_ms": 2.0},
    )
    g = ComponentGraph(nodes=[n])
    assert _graph_p95_ms(g) == pytest.approx(2.0)


def test_observed_metadata_raises_confidence():
    """All nodes with observed metrics → confidence closer to 0.9."""
    n1 = ComponentNode(id="a", label="A", tier="standard", component_type="service",
                       metadata={"p95_latency_ms": 5.0})
    n2 = ComponentNode(id="b", label="B", tier="standard", component_type="database",
                       metadata={"p95_latency_ms": 10.0})
    g = ComponentGraph(nodes=[n1, n2])
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].confidence >= 0.85


def test_heuristic_only_confidence_lower():
    g = make_graph(("api", "service"), ("db", "database"), ("q", "queue"))
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].confidence < 0.85


# ── Assumptions ───────────────────────────────────────────────────────────────

def test_assumptions_populated_for_heuristic_nodes():
    g = make_graph(("api", "service"), ("db", "database"))
    s = make_session(g)
    result = run(s, g)
    out = result["performance_review"]
    assert len(out.assumptions) == len(g.nodes)  # all heuristic
    assert all("heuristic" in a.lower() for a in out.assumptions)


def test_no_assumptions_when_all_observed():
    n1 = ComponentNode(id="a", label="A", tier="standard", component_type="service",
                       metadata={"p95_latency_ms": 5.0})
    g = ComponentGraph(nodes=[n1])
    s = make_session(g)
    result = run(s, g)
    assert result["performance_review"].assumptions == []


# ── Helper unit tests ─────────────────────────────────────────────────────────

def test_score_zero_delta_is_half():
    assert _score_from_latency_delta_pct(0.0, OptimizationGoal.BALANCED) == pytest.approx(0.5)


def test_score_negative_delta_above_half():
    assert _score_from_latency_delta_pct(-50.0, OptimizationGoal.BALANCED) > 0.5


def test_score_large_positive_delta_low():
    assert _score_from_latency_delta_pct(100.0, OptimizationGoal.BALANCED) < 0.5


def test_status_pass_for_no_risk():
    assert _status_from_risks(0.0, "low", "low", False) == ReviewerStatus.PASS


def test_status_fail_for_high_db_risk():
    assert _status_from_risks(0.0, "high", "low", False) == ReviewerStatus.FAIL


def test_status_fail_for_tier1_risk():
    assert _status_from_risks(5.0, "low", "low", True) == ReviewerStatus.FAIL
