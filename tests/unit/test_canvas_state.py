from __future__ import annotations

import pytest

from isa_cad.core.models.enums import OptimizationGoal
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)


def make_graph() -> ComponentGraph:
    return ComponentGraph(
        nodes=[
            ComponentNode(id="api", label="Orders API", tier="standard"),
            ComponentNode(id="db", label="Shared DB", tier="tier_1"),
            ComponentNode(id="auth", label="Auth0", tier="tier_1"),
            ComponentNode(id="log", label="Logger", tier="auxiliary"),
        ],
        edges=[
            ComponentEdge(source_id="api", target_id="db"),
            ComponentEdge(source_id="api", target_id="auth"),
            ComponentEdge(source_id="api", target_id="log"),
        ],
    )


def make_session(session_id: str = "session-001") -> CanvasSessionState:
    return CanvasSessionState(
        session_id=session_id,
        baseline_ref="architecture.baseline.prod",
        baseline_graph=make_graph(),
        optimization_goal=OptimizationGoal.COST_EFFICIENCY,
    )


# ── ComponentGraph ──────────────────────────────────────────────────────────

def test_get_node_found():
    g = make_graph()
    node = g.get_node("db")
    assert node is not None and node.label == "Shared DB"


def test_get_node_not_found():
    assert make_graph().get_node("nonexistent") is None


def test_neighbors():
    g = make_graph()
    neighbors = g.neighbors("api")
    assert set(neighbors) == {"db", "auth", "log"}


def test_bfs_distances():
    g = make_graph()
    dists = g.bfs_distances("api", max_depth=3)
    assert dists["db"] == 1
    assert dists["auth"] == 1
    assert dists["log"] == 1


def test_bfs_max_depth():
    # depth=0 → no neighbors returned
    g = make_graph()
    dists = g.bfs_distances("api", max_depth=0)
    assert dists == {}


# ── SandboxLayer ────────────────────────────────────────────────────────────

def test_sandbox_layer_add_node():
    layer = SandboxLayer(
        id="layer-a",
        title="Add Lambda",
        added_nodes=[ComponentNode(id="lambda", label="Lambda fn", tier="standard")],
    )
    result = layer.apply_to(make_graph())
    ids = {n.id for n in result.nodes}
    assert "lambda" in ids
    assert "api" in ids  # original preserved


def test_sandbox_layer_remove_node():
    layer = SandboxLayer(
        id="layer-b",
        title="Remove Logger",
        removed_node_ids=["log"],
    )
    result = layer.apply_to(make_graph())
    assert "log" not in {n.id for n in result.nodes}


def test_sandbox_layer_modify_node():
    layer = SandboxLayer(
        id="layer-c",
        title="Upgrade DB tier",
        modified_nodes=[ComponentNode(id="db", label="Shared DB v2", tier="tier_1")],
    )
    result = layer.apply_to(make_graph())
    node = next(n for n in result.nodes if n.id == "db")
    assert node.label == "Shared DB v2"


def test_sandbox_layer_does_not_mutate_original():
    original = make_graph()
    original_node_count = len(original.nodes)
    layer = SandboxLayer(
        id="layer-d",
        title="Add node",
        added_nodes=[ComponentNode(id="new", label="New", tier="standard")],
    )
    layer.apply_to(original)
    assert len(original.nodes) == original_node_count


# ── CanvasSessionState ───────────────────────────────────────────────────────

def test_session_add_layer():
    session = make_session()
    layer = SandboxLayer(id="layer-x", title="X")
    session.add_layer(layer)
    assert session.get_layer("layer-x") is not None


def test_session_duplicate_layer_raises():
    session = make_session()
    layer = SandboxLayer(id="layer-dup", title="Dup")
    session.add_layer(layer)
    with pytest.raises(ValueError, match="already exists"):
        session.add_layer(layer)


def test_session_activate_deactivate_layer():
    session = make_session()
    session.add_layer(SandboxLayer(id="layer-a", title="A"))
    session.activate_layer("layer-a")
    assert "layer-a" in session.active_layer_ids
    session.deactivate_layer("layer-a")
    assert "layer-a" not in session.active_layer_ids


def test_session_activate_nonexistent_raises():
    session = make_session()
    with pytest.raises(ValueError, match="not found"):
        session.activate_layer("ghost-layer")


def test_session_resolved_graph_empty_layers():
    session = make_session()
    resolved = session.resolved_graph()
    assert len(resolved.nodes) == len(session.baseline_graph.nodes)


def test_session_resolved_graph_with_active_layer():
    session = make_session()
    layer = SandboxLayer(
        id="layer-add",
        title="Add Lambda",
        added_nodes=[ComponentNode(id="lambda", label="Lambda", tier="standard")],
    )
    session.add_layer(layer)
    session.activate_layer("layer-add")
    resolved = session.resolved_graph()
    assert "lambda" in {n.id for n in resolved.nodes}


def test_session_mark_refreshed():
    session = make_session()
    session.mark_stale()
    assert session.observed_graph_stale
    session.mark_refreshed()
    assert not session.observed_graph_stale
    assert session.last_observed_graph_refresh is not None


def test_session_empty_id_raises():
    with pytest.raises(ValueError):
        CanvasSessionState(session_id="  ", baseline_ref="baseline.prod")
