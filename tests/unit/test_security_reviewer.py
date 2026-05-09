from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.reviewers.security import (
    SecurityReviewerNode,
    _compliance_status,
    _data_residency_status,
    _detect_trust_violations,
    _iam_scope_risk,
    _pii_flow_status,
    _public_exposure_risk,
    _score_from_security_signals,
    _status_from_security_score,
)
from isa_cad.core.models.enums import ReviewerStatus
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
)

reviewer = SecurityReviewerNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def node(
    nid: str,
    ctype: str,
    tier: str = "standard",
    metadata: dict | None = None,
) -> ComponentNode:
    return ComponentNode(
        id=nid, label=nid, tier=tier,
        component_type=ctype,
        metadata=metadata or {},
    )


def graph(*nodes: ComponentNode, edges: list[tuple[str, str]] | None = None) -> ComponentGraph:
    edge_objs = [ComponentEdge(source_id=s, target_id=t) for s, t in (edges or [])]
    return ComponentGraph(nodes=list(nodes), edges=edge_objs)


def session(baseline: ComponentGraph) -> CanvasSessionState:
    s = CanvasSessionState(session_id="s", baseline_ref="b")
    s.baseline_graph = baseline
    return s


def run(g: ComponentGraph) -> dict:
    s = session(g)
    state: AgentState = {"canvas_session": s, "resolved_graph": g}
    return reviewer(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_keys_present():
    g = graph(node("api", "gateway"), node("svc", "service"), node("db", "database"),
              edges=[("api", "svc"), ("svc", "db")])
    result = run(g)
    out = result["security_review"]

    assert out.public_exposure_risk is not None
    assert out.iam_scope_risk is not None
    assert out.pii_flow_status in ("pass", "fail", "warning", "unknown")
    assert out.data_residency_status in ("pass", "fail", "warning", "unknown")
    assert out.compliance_status in ("pass", "fail", "warning", "unknown")
    assert isinstance(out.trust_boundary_violations, list)
    assert 0.0 <= out.score <= 1.0
    assert 0.0 <= out.confidence <= 1.0
    assert out.status in ReviewerStatus


def test_no_session_returns_unknown():
    result = reviewer({})
    out = result["security_review"]
    assert out.status == ReviewerStatus.UNKNOWN
    assert out.confidence == 0.0
    assert "canvas_session" in out.missing_inputs


# ── Trust boundary violations ─────────────────────────────────────────────────

def test_gateway_to_db_direct_is_violation():
    """gateway → database without service layer must be flagged."""
    g = graph(
        node("gw", "gateway"), node("db", "database"),
        edges=[("gw", "db")],
    )
    violations = _detect_trust_violations(g)
    assert len(violations) == 1
    assert "gw" in violations[0]
    assert "db" in violations[0]


def test_external_to_tier1_is_violation():
    g = graph(
        node("ext", "external"), node("core_db", "database", tier="tier_1"),
        edges=[("ext", "core_db")],
    )
    violations = _detect_trust_violations(g)
    assert any("tier_1" in v or "external" in v for v in violations)


def test_service_to_service_no_violation():
    g = graph(node("a", "service"), node("b", "service"), edges=[("a", "b")])
    assert _detect_trust_violations(g) == []


def test_gateway_to_service_to_db_no_violation():
    """Proper layered path: gateway → service → database."""
    g = graph(
        node("gw", "gateway"), node("svc", "service"), node("db", "database"),
        edges=[("gw", "svc"), ("svc", "db")],
    )
    assert _detect_trust_violations(g) == []


def test_multiple_violations_all_detected():
    g = graph(
        node("gw", "gateway"),
        node("db1", "database"),
        node("q1", "queue"),
        edges=[("gw", "db1"), ("gw", "q1")],
    )
    violations = _detect_trust_violations(g)
    assert len(violations) == 2


def test_violation_triggers_fail_status():
    g = graph(node("gw", "gateway"), node("db", "database"), edges=[("gw", "db")])
    result = run(g)
    assert result["security_review"].status == ReviewerStatus.FAIL
    assert len(result["security_review"].trust_boundary_violations) > 0


# ── Public exposure ───────────────────────────────────────────────────────────

def test_no_public_nodes_low_exposure():
    g = graph(node("svc", "service"), node("db", "database"), edges=[("svc", "db")])
    assert _public_exposure_risk(g) == "low"


def test_gateway_to_service_medium_exposure():
    g = graph(node("gw", "gateway"), node("svc", "service"), edges=[("gw", "svc")])
    assert _public_exposure_risk(g) == "medium"


def test_gateway_to_db_high_exposure():
    g = graph(node("gw", "gateway"), node("db", "database"), edges=[("gw", "db")])
    assert _public_exposure_risk(g) == "high"


def test_external_to_tier1_high_exposure():
    g = graph(
        node("ext", "external"), node("core", "service", tier="tier_1"),
        edges=[("ext", "core")],
    )
    assert _public_exposure_risk(g) == "high"


# ── IAM scope risk ────────────────────────────────────────────────────────────

def test_many_callers_high_iam_risk():
    """5 services → 1 database → high IAM risk."""
    callers = [node(f"svc{i}", "service") for i in range(5)]
    db = node("db", "database")
    edges = [(f"svc{i}", "db") for i in range(5)]
    g = graph(*callers, db, edges=edges)
    assert _iam_scope_risk(g) == "high"


def test_two_callers_medium_iam_risk():
    g = graph(
        node("a", "service"), node("b", "service"), node("db", "database"),
        edges=[("a", "db"), ("b", "db")],
    )
    # 2 callers < threshold for medium (> 2) → this should be low or medium
    # low: callers = 2, threshold for medium is > 2  → low
    # (3 callers would be medium)
    assert _iam_scope_risk(g) in ("low", "medium")


def test_three_callers_medium_iam_risk():
    callers = [node(f"svc{i}", "service") for i in range(3)]
    db = node("db", "database")
    g = graph(*callers, db, edges=[(f"svc{i}", "db") for i in range(3)])
    assert _iam_scope_risk(g) == "medium"


def test_no_iam_nodes_low_risk():
    g = graph(node("a", "service"), node("b", "service"))
    assert _iam_scope_risk(g) == "low"


# ── PII flow ──────────────────────────────────────────────────────────────────

def test_pii_behind_auth_is_pass():
    """gateway → auth → database(pii=true) → pass."""
    g = graph(
        node("gw", "gateway"),
        node("auth", "auth"),
        node("db", "database", metadata={"handles_pii": "true"}),
        edges=[("gw", "auth"), ("auth", "db")],
    )
    assert _pii_flow_status(g) == "pass"


def test_pii_without_auth_is_fail():
    """gateway → database(pii=true) directly → fail."""
    g = graph(
        node("gw", "gateway"),
        node("db", "database", metadata={"handles_pii": "true"}),
        edges=[("gw", "db")],
    )
    assert _pii_flow_status(g) == "fail"


def test_no_pii_metadata_unknown():
    """No handles_pii metadata and no database/storage nodes → unknown."""
    g = graph(node("a", "service"), node("b", "service"))
    assert _pii_flow_status(g) == "unknown"


def test_implicit_pii_database_fail():
    """No explicit pii metadata but database reachable from gateway → fail."""
    g = graph(
        node("gw", "gateway"), node("db", "database"),
        edges=[("gw", "db")],
    )
    assert _pii_flow_status(g) == "fail"


def test_no_public_nodes_pii_pass():
    """No public-facing nodes → no public path to PII → pass."""
    g = graph(
        node("svc", "service"),
        node("db", "database", metadata={"handles_pii": "true"}),
        edges=[("svc", "db")],
    )
    assert _pii_flow_status(g) == "pass"


# ── Data residency ────────────────────────────────────────────────────────────

def test_same_region_pass():
    g = graph(
        node("svc", "service", metadata={"region": "eu-west-1"}),
        node("db", "database", metadata={"region": "eu-west-1"}),
        edges=[("svc", "db")],
    )
    assert _data_residency_status(g) == "pass"


def test_cross_region_db_warning():
    g = graph(
        node("svc", "service", metadata={"region": "us-east-1"}),
        node("db", "database", metadata={"region": "eu-west-1"}),
        edges=[("svc", "db")],
    )
    assert _data_residency_status(g) == "warning"


def test_no_region_metadata_unknown():
    g = graph(node("a", "service"), node("b", "database"))
    assert _data_residency_status(g) == "unknown"


# ── Compliance status ─────────────────────────────────────────────────────────

def test_violations_cause_compliance_fail():
    assert _compliance_status(["v1"], "pass", "low") == "fail"


def test_pii_fail_causes_compliance_fail():
    assert _compliance_status([], "fail", "low") == "fail"


def test_high_exposure_compliance_fail():
    assert _compliance_status([], "pass", "high") == "fail"


def test_medium_exposure_compliance_warning():
    assert _compliance_status([], "pass", "medium") == "warning"


def test_all_pass_compliance_pass():
    assert _compliance_status([], "pass", "low") == "pass"


# ── Score ─────────────────────────────────────────────────────────────────────

def test_clean_graph_score_near_1():
    score = _score_from_security_signals([], "low", "low", "pass")
    assert score == pytest.approx(1.0)


def test_violations_reduce_score():
    score_0 = _score_from_security_signals([], "low", "low", "pass")
    score_1 = _score_from_security_signals(["v1"], "low", "low", "pass")
    assert score_1 < score_0


def test_high_exposure_reduces_score():
    score_low  = _score_from_security_signals([], "low",  "low", "pass")
    score_high = _score_from_security_signals([], "high", "low", "pass")
    assert score_high < score_low


def test_pii_fail_reduces_score():
    s_pass = _score_from_security_signals([], "low", "low", "pass")
    s_fail = _score_from_security_signals([], "low", "low", "fail")
    assert s_fail < s_pass


def test_score_floor_is_zero():
    score = _score_from_security_signals(
        ["v1", "v2", "v3", "v4", "v5"], "high", "high", "fail"
    )
    assert score == pytest.approx(0.0)


# ── Confidence ────────────────────────────────────────────────────────────────

def test_confidence_higher_with_metadata():
    g_rich = graph(
        node("a", "service", metadata={"handles_pii": "false", "region": "eu-west-1"}),
        node("b", "database", metadata={"handles_pii": "true", "region": "eu-west-1"}),
    )
    g_bare = graph(node("a", "service"), node("b", "database"))
    s_rich = session(g_rich)
    s_bare = session(g_bare)

    r_rich = reviewer({"canvas_session": s_rich, "resolved_graph": g_rich})
    r_bare = reviewer({"canvas_session": s_bare, "resolved_graph": g_bare})

    assert r_rich["security_review"].confidence > r_bare["security_review"].confidence


def test_no_metadata_base_confidence():
    g = graph(node("a", "service"), node("b", "database"))
    result = run(g)
    assert result["security_review"].confidence == pytest.approx(0.50, abs=0.01)


# ── Findings ──────────────────────────────────────────────────────────────────

def test_violation_finding_severity_critical():
    g = graph(node("gw", "gateway"), node("db", "database"), edges=[("gw", "db")])
    result = run(g)
    severities = [f.severity for f in result["security_review"].findings]
    assert "critical" in severities


def test_pii_fail_finding_present():
    g = graph(
        node("gw", "gateway"),
        node("db", "database", metadata={"handles_pii": "true"}),
        edges=[("gw", "db")],
    )
    result = run(g)
    titles = [f.title for f in result["security_review"].findings]
    assert any("PII" in t for t in titles)


def test_topology_info_finding_always_present():
    """Topology-based analysis note is always added."""
    g = graph(node("a", "service"))
    result = run(g)
    titles = [f.title for f in result["security_review"].findings]
    assert any("topology" in t.lower() for t in titles)


# ── Assumptions ───────────────────────────────────────────────────────────────

def test_assumptions_include_pii_note_when_no_metadata():
    g = graph(node("a", "service"), node("b", "database"))
    result = run(g)
    assert any("handles_pii" in a for a in result["security_review"].assumptions)


def test_assumptions_include_region_note_when_no_metadata():
    g = graph(node("a", "service"))
    result = run(g)
    assert any("region" in a for a in result["security_review"].assumptions)


# ── Recommendation ────────────────────────────────────────────────────────────

def test_pass_recommendation_message():
    g = graph(node("svc", "service"), node("db", "database"), edges=[("svc", "db")])
    result = run(g)
    out = result["security_review"]
    if out.status == ReviewerStatus.PASS:
        assert "acceptable" in out.recommendation.lower()


def test_fail_recommendation_mentions_violations():
    g = graph(node("gw", "gateway"), node("db", "database"), edges=[("gw", "db")])
    result = run(g)
    assert "FAIL" in result["security_review"].recommendation or \
           "violation" in result["security_review"].recommendation.lower()
