from __future__ import annotations

import pytest

from isa_cad.core.math_models.blast_radius import (
    BlastRadiusCalculator,
    BlastRadiusInput,
    TIER_MULTIPLIER,
    _parse_tier,
)
from isa_cad.core.models.blast_radius import BlastRadiusOutput, ImpactedComponent
from isa_cad.core.models.enums import ComponentTier
from isa_cad.state.canvas_state import ComponentEdge, ComponentGraph, ComponentNode

calc = BlastRadiusCalculator()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_graph() -> ComponentGraph:
    """
    Graph topology:
        orders-api ──► shared-db   (tier_1,   d=1)
        orders-api ──► auth0       (tier_1,   d=1)
        orders-api ──► logger      (auxiliary, d=1)
        auth0      ──► user-db     (tier_1,   d=2)
        shared-db  ──► backup-svc  (standard, d=2)
    """
    return ComponentGraph(
        nodes=[
            ComponentNode(id="orders-api", label="Orders API",      tier="standard",  component_type="service"),
            ComponentNode(id="shared-db",  label="Shared DB",       tier="tier_1",    component_type="database"),
            ComponentNode(id="auth0",      label="Auth0",           tier="tier_1",    component_type="auth"),
            ComponentNode(id="logger",     label="Logger",          tier="auxiliary", component_type="logging"),
            ComponentNode(id="user-db",    label="User DB",         tier="tier_1",    component_type="database"),
            ComponentNode(id="backup-svc", label="Backup Service",  tier="standard",  component_type="service"),
        ],
        edges=[
            ComponentEdge(source_id="orders-api", target_id="shared-db"),
            ComponentEdge(source_id="orders-api", target_id="auth0"),
            ComponentEdge(source_id="orders-api", target_id="logger"),
            ComponentEdge(source_id="auth0",      target_id="user-db"),
            ComponentEdge(source_id="shared-db",  target_id="backup-svc"),
        ],
    )


# ── TIER_MULTIPLIER table ─────────────────────────────────────────────────────

def test_tier_multiplier_values():
    assert TIER_MULTIPLIER[ComponentTier.TIER_1]    == pytest.approx(2.0)
    assert TIER_MULTIPLIER[ComponentTier.STANDARD]  == pytest.approx(1.0)
    assert TIER_MULTIPLIER[ComponentTier.AUXILIARY] == pytest.approx(0.5)


# ── _parse_tier helper ────────────────────────────────────────────────────────

def test_parse_tier_known_values():
    assert _parse_tier("tier_1")    == ComponentTier.TIER_1
    assert _parse_tier("tier1")     == ComponentTier.TIER_1
    assert _parse_tier("standard")  == ComponentTier.STANDARD
    assert _parse_tier("auxiliary") == ComponentTier.AUXILIARY
    assert _parse_tier("aux")       == ComponentTier.AUXILIARY


def test_parse_tier_unknown_defaults_to_standard():
    assert _parse_tier("unknown_tier") == ComponentTier.STANDARD


# ── ImpactedComponent formula ─────────────────────────────────────────────────

def test_impact_score_tier1_d1():
    # (1.0 * 2.0) * 0.5^0 = 2.0
    c = ImpactedComponent.from_tier("db", ComponentTier.TIER_1, distance=1, base_impact=1.0, risk="r")
    assert c.impact_score == pytest.approx(2.0)


def test_impact_score_tier1_d2():
    # (1.0 * 2.0) * 0.5^1 = 1.0
    c = ImpactedComponent.from_tier("db", ComponentTier.TIER_1, distance=2, base_impact=1.0, risk="r")
    assert c.impact_score == pytest.approx(1.0)


def test_impact_score_tier1_d3():
    # (1.0 * 2.0) * 0.5^2 = 0.5
    c = ImpactedComponent.from_tier("db", ComponentTier.TIER_1, distance=3, base_impact=1.0, risk="r")
    assert c.impact_score == pytest.approx(0.5)


def test_impact_score_standard_d1():
    # (1.0 * 1.0) * 0.5^0 = 1.0
    c = ImpactedComponent.from_tier("svc", ComponentTier.STANDARD, distance=1, base_impact=1.0, risk="r")
    assert c.impact_score == pytest.approx(1.0)


def test_impact_score_auxiliary_d1():
    # (1.0 * 0.5) * 0.5^0 = 0.5
    c = ImpactedComponent.from_tier("log", ComponentTier.AUXILIARY, distance=1, base_impact=1.0, risk="r")
    assert c.impact_score == pytest.approx(0.5)


def test_impact_score_decay_halves_per_level():
    scores = [
        ImpactedComponent.from_tier("c", ComponentTier.STANDARD, d, 1.0, "r").impact_score
        for d in range(1, 5)
    ]
    for i in range(len(scores) - 1):
        assert scores[i + 1] == pytest.approx(scores[i] * 0.5, abs=0.0001)


# ── BlastRadiusCalculator.compute ────────────────────────────────────────────

def test_compute_returns_all_reachable_nodes():
    graph = make_graph()
    result = calc.compute(BlastRadiusInput("orders-api", graph, max_depth=3))

    impacted_ids = {c.id for c in result.impacted_stable_components}
    assert "shared-db"  in impacted_ids
    assert "auth0"      in impacted_ids
    assert "logger"     in impacted_ids
    assert "user-db"    in impacted_ids
    assert "backup-svc" in impacted_ids
    assert "orders-api" not in impacted_ids   # source excluded


def test_compute_correct_distances():
    graph = make_graph()
    result = calc.compute(BlastRadiusInput("orders-api", graph, max_depth=3))
    by_id = {c.id: c for c in result.impacted_stable_components}

    assert by_id["shared-db"].distance  == 1
    assert by_id["auth0"].distance      == 1
    assert by_id["logger"].distance     == 1
    assert by_id["user-db"].distance    == 2
    assert by_id["backup-svc"].distance == 2


def test_compute_tier1_d1_impact_score():
    graph = make_graph()
    result = calc.compute(BlastRadiusInput("orders-api", graph))
    by_id = {c.id: c for c in result.impacted_stable_components}

    # shared-db: tier_1, d=1 → (1.0 * 2.0) * 0.5^0 = 2.0
    assert by_id["shared-db"].impact_score  == pytest.approx(2.0)
    # auth0: tier_1, d=1 → 2.0
    assert by_id["auth0"].impact_score      == pytest.approx(2.0)
    # logger: auxiliary, d=1 → (1.0 * 0.5) * 1 = 0.5
    assert by_id["logger"].impact_score     == pytest.approx(0.5)
    # user-db: tier_1, d=2 → (1.0 * 2.0) * 0.5 = 1.0
    assert by_id["user-db"].impact_score    == pytest.approx(1.0)
    # backup-svc: standard, d=2 → (1.0 * 1.0) * 0.5 = 0.5
    assert by_id["backup-svc"].impact_score == pytest.approx(0.5)


def test_compute_total_impact_score():
    graph = make_graph()
    result = calc.compute(BlastRadiusInput("orders-api", graph))
    expected = 2.0 + 2.0 + 0.5 + 1.0 + 0.5
    assert result.total_impact_score == pytest.approx(expected)


def test_compute_high_risk_count():
    graph = make_graph()
    result = calc.compute(BlastRadiusInput("orders-api", graph))
    # tier_1 components with impact >= 1.0: shared-db(2.0), auth0(2.0), user-db(1.0)
    assert result.high_risk_count == 3


def test_compute_max_depth_limits_traversal():
    graph = make_graph()
    result_d1 = calc.compute(BlastRadiusInput("orders-api", graph, max_depth=1))
    result_d2 = calc.compute(BlastRadiusInput("orders-api", graph, max_depth=2))

    ids_d1 = {c.id for c in result_d1.impacted_stable_components}
    ids_d2 = {c.id for c in result_d2.impacted_stable_components}

    # depth=1: only direct neighbours
    assert "user-db"    not in ids_d1
    assert "backup-svc" not in ids_d1
    assert "shared-db"  in ids_d1

    # depth=2: includes d=2 nodes
    assert "user-db"    in ids_d2
    assert "backup-svc" in ids_d2


def test_compute_isolated_source_no_impact():
    graph = ComponentGraph(
        nodes=[ComponentNode(id="solo", label="Solo", tier="standard")],
        edges=[],
    )
    result = calc.compute(BlastRadiusInput("solo", graph))
    assert result.impacted_stable_components == []
    assert result.total_impact_score == 0.0


def test_compute_risk_override():
    graph = make_graph()
    overrides = {"shared-db": ("custom_risk", ["custom mitigation"])}
    result = calc.compute(BlastRadiusInput("orders-api", graph, risk_overrides=overrides))
    by_id = {c.id: c for c in result.impacted_stable_components}

    assert by_id["shared-db"].risk == "custom_risk"
    assert by_id["shared-db"].mitigations == ["custom mitigation"]


def test_compute_summary_contains_source():
    graph = make_graph()
    result = calc.compute(BlastRadiusInput("orders-api", graph))
    assert "orders-api" in result.summary
    assert "Severity" in result.summary


def test_compute_summary_empty_graph():
    graph = ComponentGraph(
        nodes=[ComponentNode(id="lone", label="Lone", tier="standard")],
        edges=[],
    )
    result = calc.compute(BlastRadiusInput("lone", graph))
    assert "No stable components" in result.summary


# ── BlastRadiusCalculator.diff ────────────────────────────────────────────────

def test_diff_new_component_detected():
    graph  = make_graph()
    base   = calc.compute(BlastRadiusInput("orders-api", graph, max_depth=1))

    # Proposed: add a new Tier-1 node at d=1
    from isa_cad.state.canvas_state import SandboxLayer
    layer = SandboxLayer(
        id="l", title="L",
        added_nodes=[ComponentNode(id="payments-db", label="Payments DB", tier="tier_1")],
        added_edges=[ComponentEdge(source_id="orders-api", target_id="payments-db")],
    )
    proposed_graph = layer.apply_to(graph)
    proposed = calc.compute(BlastRadiusInput("orders-api", proposed_graph, max_depth=1))

    diff = calc.diff(base, proposed)
    assert "payments-db" in diff["new_components"]
    assert diff["total_delta"] > 0


def test_diff_removed_component_detected():
    graph = make_graph()
    base  = calc.compute(BlastRadiusInput("orders-api", graph, max_depth=1))

    from isa_cad.state.canvas_state import SandboxLayer
    layer = SandboxLayer(
        id="l", title="L",
        removed_node_ids=["logger"],
        removed_edge_keys=[("orders-api", "logger")],
    )
    proposed_graph = layer.apply_to(graph)
    proposed = calc.compute(BlastRadiusInput("orders-api", proposed_graph, max_depth=1))

    diff = calc.diff(base, proposed)
    assert "logger" in diff["removed_components"]


def test_diff_score_change_tracked():
    # Start with a standard node, then upgrade it to tier_1 via sandbox layer
    graph = ComponentGraph(
        nodes=[
            ComponentNode(id="api",    label="API",    tier="standard"),
            ComponentNode(id="worker", label="Worker", tier="standard"),
        ],
        edges=[ComponentEdge(source_id="api", target_id="worker")],
    )
    base     = calc.compute(BlastRadiusInput("api", graph))
    # worker: standard, d=1 → score = 1.0

    from isa_cad.state.canvas_state import SandboxLayer
    layer = SandboxLayer(
        id="l", title="L",
        modified_nodes=[ComponentNode(id="worker", label="Worker", tier="tier_1")],
    )
    proposed_graph = layer.apply_to(graph)
    proposed = calc.compute(BlastRadiusInput("api", proposed_graph))
    # worker: tier_1, d=1 → score = 2.0

    diff = calc.diff(base, proposed)
    changes = {c["id"]: c for c in diff["score_changes"]}
    assert "worker" in changes
    assert changes["worker"]["delta"] == pytest.approx(1.0)
