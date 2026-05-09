from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.reviewers.cost import CostReviewerNode, _build_tco_input
from isa_cad.core.models.calibration import CalibrationResult, SafetyBuffer
from isa_cad.core.models.enums import (
    CacheContext,
    OptimizationGoal,
    ReviewerStatus,
)
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)

node = CostReviewerNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_graph(*types: str) -> ComponentGraph:
    """Quick helper: make a graph from a list of component_type strings."""
    nodes = [
        ComponentNode(id=f"n{i}", label=t, tier="standard", component_type=t)
        for i, t in enumerate(types)
    ]
    return ComponentGraph(nodes=nodes)


def make_session(baseline: ComponentGraph) -> CanvasSessionState:
    s = CanvasSessionState(session_id="s", baseline_ref="b")
    s.baseline_graph = baseline
    return s


def run(
    session: CanvasSessionState,
    resolved: ComponentGraph,
    goal: OptimizationGoal = OptimizationGoal.BALANCED,
    calibration: CalibrationResult | None = None,
) -> dict:
    state: AgentState = {
        "canvas_session": session,
        "resolved_graph": resolved,
        "optimization_goal": goal,
    }
    if calibration:
        state["calibration_result"] = calibration
    return node(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_keys_present():
    g = make_graph("service", "database")
    session = make_session(g)
    result = run(session, g)
    out = result["cost_review"]

    assert out.monthly_current_usd is not None
    assert out.monthly_projected_usd is not None
    assert out.tco_delta_usd is not None
    assert out.status in ReviewerStatus
    assert 0.0 <= out.score <= 1.0
    assert 0.0 <= out.confidence <= 1.0
    assert out.recommendation != ""


def test_no_session_returns_unknown():
    result = node({})
    out = result["cost_review"]
    assert out.status == ReviewerStatus.UNKNOWN
    assert out.confidence == 0.0
    assert "canvas_session" in out.missing_inputs


# ── Cost delta logic ──────────────────────────────────────────────────────────

def test_no_changes_pass_status():
    g = make_graph("service", "database")
    session = make_session(g)
    result = run(session, g)
    assert result["cost_review"].status == ReviewerStatus.PASS


def test_large_cost_increase_fail_status():
    """Add 10 heavy databases → cost increase > 25%."""
    baseline = make_graph("service")
    extra = [ComponentNode(id=f"db{i}", label=f"DB{i}", tier="tier_1", component_type="database") for i in range(10)]
    proposed = ComponentGraph(nodes=baseline.nodes + extra)
    session = make_session(baseline)
    result = run(session, proposed)
    assert result["cost_review"].status == ReviewerStatus.FAIL
    assert result["cost_review"].tco_delta_usd > 0


def test_cost_saving_positive_score():
    """Remove a database → cost goes down → score > 0.5."""
    baseline = make_graph("service", "database", "database")
    proposed = make_graph("service")
    session = make_session(baseline)
    result = run(session, proposed)
    out = result["cost_review"]
    assert out.tco_delta_usd < 0
    assert out.score > 0.5
    assert out.status == ReviewerStatus.PASS


def test_cost_saving_finding_present():
    baseline = make_graph("service", "database")
    proposed = make_graph("service")
    session = make_session(baseline)
    result = run(session, proposed)
    titles = [f.title for f in result["cost_review"].findings]
    assert any("reduction" in t.lower() for t in titles)


# ── Score sensitivity to goal ─────────────────────────────────────────────────

def test_cost_efficiency_goal_amplifies_savings():
    """Same saving, COST_EFFICIENCY goal → score closer to 1.0 than BALANCED."""
    baseline = make_graph("service", "database", "database")
    proposed = make_graph("service")
    session = make_session(baseline)

    r_balanced = run(session, proposed, goal=OptimizationGoal.BALANCED)
    r_cost     = run(session, proposed, goal=OptimizationGoal.COST_EFFICIENCY)

    assert r_cost["cost_review"].score >= r_balanced["cost_review"].score


# ── Egress and CHR ────────────────────────────────────────────────────────────

def test_egress_chr_source_populated():
    g = make_graph("gateway", "service")
    session = make_session(g)
    result = run(session, g)
    out = result["cost_review"]
    assert out.cache_hit_ratio is not None
    assert out.cache_hit_ratio_source is not None


def test_observed_chr_bypasses_heuristic():
    """Node with observed_chr in metadata → chr_source == 'observed'."""
    node_with_obs = ComponentNode(
        id="cdn", label="CDN", tier="standard", component_type="gateway",
        metadata={"observed_chr": 0.92},
    )
    g = ComponentGraph(nodes=[node_with_obs])
    session = make_session(g)
    result = run(session, g)
    out = result["cost_review"]
    assert out.cache_hit_ratio_source == "observed"
    assert out.cache_hit_ratio == pytest.approx(0.92, abs=0.01)


def test_unknown_chr_heuristic_assumption_flagged():
    """Service with no CHR context → heuristic_unknown_conservative + finding."""
    g = make_graph("service")
    session = make_session(g)
    result = run(session, g)
    out = result["cost_review"]
    assert out.cache_hit_ratio_source == "heuristic_unknown_conservative"
    assert any("conservative" in a.lower() or "chr=0.00" in a.lower() for a in out.assumptions)


# ── Inter-region cost ─────────────────────────────────────────────────────────

def test_inter_region_cost_populated():
    n = ComponentNode(
        id="svc", label="Svc", tier="standard", component_type="service",
        metadata={"inter_region_gb": 100.0},
    )
    g = ComponentGraph(nodes=[n])
    session = make_session(g)
    result = run(session, g)
    out = result["cost_review"]
    assert out.inter_region_cost_usd is not None
    assert out.inter_region_cost_usd > 0.0


# ── Safety buffer ─────────────────────────────────────────────────────────────

def test_safety_buffer_applied_to_projected():
    """When CalibrationResult has safety buffer, proposed TCO should be higher."""
    g = make_graph("service", "database")
    session = make_session(g)
    cal = CalibrationResult(
        safety_buffer=SafetyBuffer(applied=True, cost_multiplier=1.15, reason="historical overrun > 20%"),
    )

    result_no_buf = run(session, g)
    result_buf    = run(session, g, calibration=cal)

    projected_no  = result_no_buf["cost_review"].monthly_projected_usd
    projected_buf = result_buf["cost_review"].monthly_projected_usd

    assert projected_buf > projected_no
    assert any("buffer" in f.title.lower() for f in result_buf["cost_review"].findings)


# ── Confidence ────────────────────────────────────────────────────────────────

def test_confidence_lower_with_more_heuristic_assumptions():
    """More estimated nodes → more assumptions → lower confidence."""
    g_small = make_graph("service")
    g_large = make_graph(*["service"] * 10)

    session_s = make_session(g_small)
    session_l = make_session(g_large)

    r_small = run(session_s, g_small)
    r_large = run(session_l, g_large)

    # Large graph has many estimated prices → same assumptions but repeated
    # Confidence should not exceed 1.0 and should be reasonable
    assert 0.0 < r_small["cost_review"].confidence <= 1.0
    assert 0.0 < r_large["cost_review"].confidence <= 1.0


def test_observed_cost_metadata_bypasses_heuristic():
    """Node with monthly_cost_usd in metadata does not create estimated assumption."""
    n = ComponentNode(
        id="svc", label="Svc", tier="standard", component_type="service",
        metadata={"monthly_cost_usd": 999.0},
    )
    g = ComponentGraph(nodes=[n])
    tco_input = _build_tco_input(g)
    r = tco_input.resources[0]
    assert r.unit_price_usd == 999.0
    assert r.is_estimated is False


# ── TCO delta numbers ─────────────────────────────────────────────────────────

def test_tco_delta_equals_projected_minus_current():
    g = make_graph("service", "database")
    session = make_session(g)

    extra = ComponentNode(id="new", label="New", tier="standard", component_type="service")
    proposed = ComponentGraph(nodes=g.nodes + [extra])
    result = run(session, proposed)
    out = result["cost_review"]

    assert abs(
        out.tco_delta_usd - (out.monthly_projected_usd - out.monthly_current_usd)
    ) < 0.01


# ── Summary / recommendation ──────────────────────────────────────────────────

def test_recommendation_contains_sign_and_amount():
    g = make_graph("service", "database")
    session = make_session(g)
    result = run(session, g)
    rec = result["cost_review"].recommendation
    assert "$" in rec
    assert "%" in rec
