from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.build_design_delta import BuildDesignDeltaNode, DesignDelta
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)

node = BuildDesignDeltaNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_baseline() -> ComponentGraph:
    return ComponentGraph(
        nodes=[
            ComponentNode(id="api",    label="API",       tier="standard",  component_type="service"),
            ComponentNode(id="db",     label="Shared DB", tier="tier_1",    component_type="database"),
            ComponentNode(id="logger", label="Logger",    tier="auxiliary", component_type="logging"),
        ],
        edges=[
            ComponentEdge(source_id="api", target_id="db"),
            ComponentEdge(source_id="api", target_id="logger"),
        ],
    )


def make_session_with_layer(layer: SandboxLayer) -> tuple[CanvasSessionState, ComponentGraph]:
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = make_baseline()
    session.add_layer(layer)
    session.activate_layer(layer.id)
    resolved = session.resolved_graph()
    return session, resolved


def run_node(session: CanvasSessionState, resolved: ComponentGraph) -> dict:
    state: AgentState = {"canvas_session": session, "resolved_graph": resolved}
    return node(state)


# ── DesignDelta model ─────────────────────────────────────────────────────────

def test_no_changes_has_changes_false():
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = make_baseline()
    resolved = session.resolved_graph()
    result = run_node(session, resolved)

    delta = result["design_delta"]
    assert delta["has_changes"] is False
    assert "No structural changes" in delta["summary"]


def test_to_dict_contains_all_keys():
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = make_baseline()
    result = run_node(session, session.resolved_graph())
    delta = result["design_delta"]

    for key in (
        "baseline_node_count", "proposed_node_count",
        "baseline_edge_count", "proposed_edge_count",
        "added_nodes", "removed_nodes", "modified_nodes",
        "added_edges", "removed_edges",
        "primary_source_id", "contributing_layers",
        "has_changes", "summary",
    ):
        assert key in delta, f"Missing key: {key}"


# ── Added node ────────────────────────────────────────────────────────────────

def test_added_node_detected():
    layer = SandboxLayer(
        id="l",
        title="Add Lambda",
        added_nodes=[ComponentNode(id="lambda", label="Lambda", tier="standard")],
        added_edges=[ComponentEdge(source_id="api", target_id="lambda")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    delta = result["design_delta"]

    added_ids = [n["id"] for n in delta["added_nodes"]]
    assert "lambda" in added_ids
    assert delta["has_changes"] is True
    assert "+1 node" in delta["summary"]


def test_added_node_becomes_primary_source():
    layer = SandboxLayer(
        id="l",
        title="Add Lambda",
        added_nodes=[ComponentNode(id="lambda", label="Lambda", tier="standard")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    assert result["source_component_id"] == "lambda"


def test_added_edge_detected():
    layer = SandboxLayer(
        id="l",
        title="New edge",
        added_nodes=[ComponentNode(id="svc", label="Svc", tier="standard")],
        added_edges=[ComponentEdge(source_id="api", target_id="svc")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    delta = result["design_delta"]

    added_edge_pairs = [(e["source_id"], e["target_id"]) for e in delta["added_edges"]]
    assert ("api", "svc") in added_edge_pairs


# ── Removed node ──────────────────────────────────────────────────────────────

def test_removed_node_detected():
    layer = SandboxLayer(
        id="l",
        title="Remove logger",
        removed_node_ids=["logger"],
        removed_edge_keys=[("api", "logger")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    delta = result["design_delta"]

    removed_ids = [n["id"] for n in delta["removed_nodes"]]
    assert "logger" in removed_ids
    assert delta["has_changes"] is True


def test_removed_node_primary_source_is_neighbour():
    layer = SandboxLayer(
        id="l",
        title="Remove logger",
        removed_node_ids=["logger"],
        removed_edge_keys=[("api", "logger")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    # logger's neighbour in baseline is "api"
    assert result["source_component_id"] == "api"


def test_removed_edge_detected():
    layer = SandboxLayer(
        id="l",
        title="Remove edge",
        removed_edge_keys=[("api", "logger")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    delta = result["design_delta"]

    removed_pairs = [(e["source_id"], e["target_id"]) for e in delta["removed_edges"]]
    assert ("api", "logger") in removed_pairs


# ── Modified node ─────────────────────────────────────────────────────────────

def test_modified_node_detected():
    layer = SandboxLayer(
        id="l",
        title="Upgrade db tier",
        modified_nodes=[ComponentNode(id="db", label="Shared DB v2", tier="tier_1")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    delta = result["design_delta"]

    modified_ids = [n["id"] for n in delta["modified_nodes"]]
    assert "db" in modified_ids


def test_modified_node_becomes_primary_source_when_no_additions():
    layer = SandboxLayer(
        id="l",
        title="Change API",
        modified_nodes=[ComponentNode(id="api", label="API v2", tier="standard", component_type="gateway")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    assert result["source_component_id"] == "api"


# ── Node/edge counts ──────────────────────────────────────────────────────────

def test_counts_reflect_baseline():
    session = CanvasSessionState(session_id="s", baseline_ref="b")
    session.baseline_graph = make_baseline()
    result = run_node(session, session.resolved_graph())
    delta = result["design_delta"]

    assert delta["baseline_node_count"] == 3
    assert delta["proposed_node_count"] == 3
    assert delta["baseline_edge_count"] == 2
    assert delta["proposed_edge_count"] == 2


def test_counts_after_add():
    layer = SandboxLayer(
        id="l", title="Add node+edge",
        added_nodes=[ComponentNode(id="new", label="New", tier="standard")],
        added_edges=[ComponentEdge(source_id="api", target_id="new")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    delta = result["design_delta"]

    assert delta["proposed_node_count"] == delta["baseline_node_count"] + 1
    assert delta["proposed_edge_count"] == delta["baseline_edge_count"] + 1


# ── Contributing layers ───────────────────────────────────────────────────────

def test_contributing_layers_populated():
    layer = SandboxLayer(
        id="layer-a", title="A",
        added_nodes=[ComponentNode(id="x", label="X", tier="standard")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    assert "layer-a" in result["design_delta"]["contributing_layers"]


# ── Missing state graceful handling ──────────────────────────────────────────

def test_no_session_returns_empty_delta():
    result = node({})
    assert result["design_delta"]["has_changes"] is False
    assert result["source_component_id"] == ""


# ── Multiple changes in summary ───────────────────────────────────────────────

def test_summary_covers_all_change_types():
    layer = SandboxLayer(
        id="l", title="Multi",
        added_nodes=[ComponentNode(id="new-svc", label="New Svc", tier="standard")],
        removed_node_ids=["logger"],
        modified_nodes=[ComponentNode(id="db", label="DB v2", tier="tier_1")],
        added_edges=[ComponentEdge(source_id="api", target_id="new-svc")],
        removed_edge_keys=[("api", "logger")],
    )
    session, resolved = make_session_with_layer(layer)
    result = run_node(session, resolved)
    summary = result["design_delta"]["summary"]

    assert "+" in summary   # additions
    assert "-" in summary   # removals
    assert "~" in summary   # modifications
