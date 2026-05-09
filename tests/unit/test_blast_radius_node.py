from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.blast_radius import BlastRadiusNode, _DEFAULT_MAX_DEPTH
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.core.models.enums import ComponentTier
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
)

node = BlastRadiusNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def n(nid: str, ctype: str = "service", tier: str = "standard") -> ComponentNode:
    return ComponentNode(id=nid, label=nid, tier=tier, component_type=ctype)


def graph(*nodes: ComponentNode, edges: list[tuple[str, str]] | None = None) -> ComponentGraph:
    edge_objs = [ComponentEdge(source_id=s, target_id=t) for s, t in (edges or [])]
    return ComponentGraph(nodes=list(nodes), edges=edge_objs)


def session(baseline: ComponentGraph) -> CanvasSessionState:
    s = CanvasSessionState(session_id="s", baseline_ref="b")
    s.baseline_graph = baseline
    return s


def run(
    source_id: str,
    resolved: ComponentGraph,
    sess: CanvasSessionState | None = None,
) -> dict:
    state: AgentState = {
        "source_component_id": source_id,
        "resolved_graph": resolved,
    }
    if sess:
        state["canvas_session"] = sess
    return node(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_blast_radius_key_present():
    g = graph(n("api"), n("db", "database"), edges=[("api", "db")])
    result = run("api", g)
    assert "blast_radius" in result
    assert isinstance(result["blast_radius"], BlastRadiusOutput)


def test_output_fields_populated():
    g = graph(n("api"), n("db", "database"), edges=[("api", "db")])
    result = run("api", g)
    br = result["blast_radius"]
    assert br.source_component_id == "api"
    assert br.max_traversal_depth == _DEFAULT_MAX_DEPTH
    assert br.summary != ""


# ── Graceful degradation ──────────────────────────────────────────────────────

def test_no_source_id_returns_empty():
    g = graph(n("api"))
    state: AgentState = {"resolved_graph": g}
    result = node(state)
    br = result["blast_radius"]
    assert br.impacted_stable_components == []
    assert "skipped" in br.summary.lower()


def test_no_graph_returns_empty():
    state: AgentState = {"source_component_id": "api"}
    result = node(state)
    br = result["blast_radius"]
    assert br.impacted_stable_components == []
    assert "skipped" in br.summary.lower()


def test_source_not_in_graph_returns_empty():
    g = graph(n("api"), n("db", "database"))
    result = run("nonexistent", g)
    br = result["blast_radius"]
    assert br.impacted_stable_components == []
    assert "not found" in br.summary.lower()


def test_isolated_source_no_neighbours():
    g = graph(n("api"))
    result = run("api", g)
    br = result["blast_radius"]
    # BFS from api finds no neighbours → empty impacted list
    assert br.impacted_stable_components == []


# ── BFS distances ─────────────────────────────────────────────────────────────

def test_direct_neighbour_distance_1():
    g = graph(n("src"), n("nb"), edges=[("src", "nb")])
    result = run("src", g)
    br = result["blast_radius"]
    neighbour = next(c for c in br.impacted_stable_components if c.id == "nb")
    assert neighbour.distance == 1


def test_two_hop_distance_2():
    g = graph(n("src"), n("mid"), n("far"), edges=[("src", "mid"), ("mid", "far")])
    result = run("src", g)
    br = result["blast_radius"]
    ids = {c.id: c.distance for c in br.impacted_stable_components}
    assert ids["mid"] == 1
    assert ids["far"] == 2


def test_max_depth_respected():
    # Chain: src → a → b → c → d  (4 hops)
    g = graph(
        n("src"), n("a"), n("b"), n("c"), n("d"),
        edges=[("src", "a"), ("a", "b"), ("b", "c"), ("c", "d")],
    )
    result = run("src", g)
    br = result["blast_radius"]
    ids = {c.id for c in br.impacted_stable_components}
    # Default max_depth=3 → d is 4 hops away → not included
    assert "d" not in ids
    assert "c" in ids


# ── Impact score formula ──────────────────────────────────────────────────────

def test_standard_tier_d1_score_is_1():
    g = graph(n("src"), n("svc", "service", "standard"), edges=[("src", "svc")])
    result = run("src", g)
    br = result["blast_radius"]
    svc = next(c for c in br.impacted_stable_components if c.id == "svc")
    # base=1.0, C_m=1.0, d=1 → 1.0 * 1.0 * 0.5^0 = 1.0
    assert svc.impact_score == pytest.approx(1.0)


def test_tier1_d1_score_is_2():
    g = graph(n("src"), n("db", "database", "tier_1"), edges=[("src", "db")])
    result = run("src", g)
    br = result["blast_radius"]
    db = next(c for c in br.impacted_stable_components if c.id == "db")
    # base=1.0, C_m=2.0, d=1 → 2.0
    assert db.impact_score == pytest.approx(2.0)


def test_auxiliary_d1_score_is_half():
    g = graph(n("src"), n("log", "logging", "auxiliary"), edges=[("src", "log")])
    result = run("src", g)
    br = result["blast_radius"]
    log = next(c for c in br.impacted_stable_components if c.id == "log")
    # base=1.0, C_m=0.5, d=1 → 0.5
    assert log.impact_score == pytest.approx(0.5)


def test_standard_d2_score_is_half():
    g = graph(n("src"), n("a"), n("b"), edges=[("src", "a"), ("a", "b")])
    result = run("src", g)
    br = result["blast_radius"]
    b = next(c for c in br.impacted_stable_components if c.id == "b")
    # base=1.0, C_m=1.0, d=2 → 1.0 * 0.5^1 = 0.5
    assert b.impact_score == pytest.approx(0.5)


def test_tier1_d2_score_is_1():
    g = graph(n("src"), n("mid"), n("db", "database", "tier_1"),
              edges=[("src", "mid"), ("mid", "db")])
    result = run("src", g)
    br = result["blast_radius"]
    db = next(c for c in br.impacted_stable_components if c.id == "db")
    # base=1.0, C_m=2.0, d=2 → 2.0 * 0.5^1 = 1.0
    assert db.impact_score == pytest.approx(1.0)


def test_d3_score_is_quarter_for_standard():
    g = graph(n("src"), n("a"), n("b"), n("c"),
              edges=[("src", "a"), ("a", "b"), ("b", "c")])
    result = run("src", g)
    br = result["blast_radius"]
    c = next(c for c in br.impacted_stable_components if c.id == "c")
    # base=1.0, C_m=1.0, d=3 → 0.5^2 = 0.25
    assert c.impact_score == pytest.approx(0.25)


# ── Total impact and high_risk_count ─────────────────────────────────────────

def test_total_impact_score_is_sum():
    g = graph(n("src"), n("a"), n("b"), edges=[("src", "a"), ("a", "b")])
    result = run("src", g)
    br = result["blast_radius"]
    expected = sum(c.impact_score for c in br.impacted_stable_components)
    assert br.total_impact_score == pytest.approx(expected)


def test_high_risk_count_tier1_d1():
    # Tier-1 at d=1 → impact=2.0 ≥ 1.0 → high_risk
    g = graph(n("src"), n("db", "database", "tier_1"), edges=[("src", "db")])
    result = run("src", g)
    assert result["blast_radius"].high_risk_count == 1


def test_high_risk_count_zero_for_auxiliary():
    g = graph(n("src"), n("log", "logging", "auxiliary"), edges=[("src", "log")])
    result = run("src", g)
    assert result["blast_radius"].high_risk_count == 0


# ── Risk classification ───────────────────────────────────────────────────────

def test_database_node_risk_label():
    g = graph(n("src"), n("db", "database"), edges=[("src", "db")])
    result = run("src", g)
    br = result["blast_radius"]
    db = next(c for c in br.impacted_stable_components if c.id == "db")
    assert "bottleneck" in db.risk.lower() or "io" in db.risk.lower()


def test_queue_node_risk_label():
    g = graph(n("src"), n("q", "queue"), edges=[("src", "q")])
    result = run("src", g)
    br = result["blast_radius"]
    q = next(c for c in br.impacted_stable_components if c.id == "q")
    assert "queue" in db.risk.lower() or "backpressure" in q.risk.lower() \
        if (db := q) else True
    assert "backpressure" in q.risk.lower() or "queue" in q.risk.lower()


def test_mitigations_non_empty_for_database():
    g = graph(n("src"), n("db", "database"), edges=[("src", "db")])
    result = run("src", g)
    br = result["blast_radius"]
    db = next(c for c in br.impacted_stable_components if c.id == "db")
    assert len(db.mitigations) > 0


# ── Summary ───────────────────────────────────────────────────────────────────

def test_summary_contains_source_id():
    g = graph(n("api"), n("db", "database"), edges=[("api", "db")])
    result = run("api", g)
    assert "api" in result["blast_radius"].summary


def test_summary_contains_count():
    g = graph(n("src"), n("a"), n("b"), edges=[("src", "a"), ("a", "b")])
    result = run("src", g)
    # 2 impacted components
    assert "2" in result["blast_radius"].summary


def test_summary_severity_high_for_tier1():
    g = graph(n("src"), n("db", "database", "tier_1"), edges=[("src", "db")])
    result = run("src", g)
    assert "HIGH" in result["blast_radius"].summary


# ── Baseline diff ─────────────────────────────────────────────────────────────

def test_baseline_diff_present_when_source_in_baseline():
    baseline = graph(n("api"), n("db", "database"), edges=[("api", "db")])
    sess = session(baseline)
    result = run("api", baseline, sess)
    assert "blast_radius_diff" in result


def test_baseline_diff_absent_for_new_source():
    """Source node added in proposed → not in baseline → no diff."""
    baseline = graph(n("api"))
    proposed = graph(n("api"), n("new_svc"), edges=[("api", "new_svc")])
    sess = session(baseline)
    state: AgentState = {
        "source_component_id": "new_svc",
        "resolved_graph": proposed,
        "canvas_session": sess,
    }
    result = node(state)
    assert "blast_radius_diff" not in result


def test_diff_total_delta_sign():
    """Adding a Tier-1 DB to proposed → higher total impact → positive delta."""
    baseline = graph(n("api"), n("svc"), edges=[("api", "svc")])
    proposed = graph(n("api"), n("svc"), n("db", "database", "tier_1"),
                     edges=[("api", "svc"), ("svc", "db")])
    sess = session(baseline)
    state: AgentState = {
        "source_component_id": "api",
        "resolved_graph": proposed,
        "canvas_session": sess,
    }
    result = node(state)
    diff = result["blast_radius_diff"]
    assert diff["total_delta"] > 0
    assert "db" in diff["new_components"]


def test_diff_keys_present():
    baseline = graph(n("api"), n("db", "database"), edges=[("api", "db")])
    sess = session(baseline)
    result = run("api", baseline, sess)
    diff = result["blast_radius_diff"]
    for key in ("baseline_total", "proposed_total", "total_delta",
                "new_components", "removed_components",
                "score_changes", "high_risk_delta"):
        assert key in diff, f"Missing diff key: {key}"


# ── State passthrough ─────────────────────────────────────────────────────────

def test_existing_state_keys_preserved():
    g = graph(n("api"), n("db", "database"), edges=[("api", "db")])
    state: AgentState = {
        "source_component_id": "api",
        "resolved_graph": g,
        "session_id": "sess-blast",
    }
    result = node(state)
    assert result["session_id"] == "sess-blast"
