from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.context_freshness import ContextAndFreshnessNode, _infer_component_class
from isa_cad.core.models.enums import OptimizationGoal, OutputMode
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)
from isa_cad.state.checkpoint_store import CheckpointStore
from isa_cad.state.session_store import SessionStore


# ── helpers ───────────────────────────────────────────────────────────────────

def make_fresh_session(tmp_path: Path) -> tuple[CanvasSessionState, SessionStore]:
    store = SessionStore(base_dir=tmp_path / "sessions")
    session = CanvasSessionState(
        session_id="test-session",
        baseline_ref="baseline.prod",
        optimization_goal=OptimizationGoal.COST_EFFICIENCY,
        baseline_graph=ComponentGraph(
            nodes=[
                ComponentNode(id="api",    label="API",       tier="standard"),
                ComponentNode(id="db",     label="Shared DB", tier="tier_1",   component_type="database"),
                ComponentNode(id="logger", label="Logger",    tier="auxiliary", component_type="logging"),
            ],
            edges=[
                ComponentEdge(source_id="api", target_id="db"),
                ComponentEdge(source_id="api", target_id="logger"),
            ],
        ),
        last_observed_graph_refresh=datetime.now(UTC) - timedelta(hours=2),
    )
    store.save(session)
    return session, store


def make_node(tmp_path: Path, session: CanvasSessionState | None = None) -> tuple[ContextAndFreshnessNode, SessionStore]:
    session_store = SessionStore(base_dir=tmp_path / "sessions")
    checkpoint_store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    if session:
        session_store.save(session)
    node = ContextAndFreshnessNode(
        session_store=session_store,
        checkpoint_store=checkpoint_store,
    )
    return node, session_store


# ── _infer_component_class ────────────────────────────────────────────────────

def test_infer_component_class_lambda():
    assert _infer_component_class("proposal.layer-a-serverless-lambda") == "lambda"

def test_infer_component_class_ecs():
    assert _infer_component_class("proposal.layer-b-managed-ecs") == "ecs"

def test_infer_component_class_rds():
    assert _infer_component_class("proposal.migrate-postgresql-aurora") == "rds"

def test_infer_component_class_unknown():
    assert _infer_component_class("proposal.some-random-thing") == "unknown"


# ── Load existing session ────────────────────────────────────────────────────

def test_loads_existing_session(tmp_path: Path):
    session = CanvasSessionState(
        session_id="sess-001",
        baseline_ref="baseline.prod",
        optimization_goal=OptimizationGoal.MAX_RELIABILITY,
        last_observed_graph_refresh=datetime.now(UTC) - timedelta(hours=1),
    )
    node, _ = make_node(tmp_path, session)
    state: AgentState = {"session_id": "sess-001"}
    result = node(state)

    assert result["canvas_session"].session_id == "sess-001"
    assert result["optimization_goal"] == OptimizationGoal.MAX_RELIABILITY
    assert result["context_ready"] is True


def test_creates_empty_session_when_not_found(tmp_path: Path):
    node, _ = make_node(tmp_path)
    state: AgentState = {"session_id": "ghost-session", "baseline_ref": "baseline.prod"}
    result = node(state)

    assert result["canvas_session"].session_id == "ghost-session"
    assert result["context_ready"] is False
    assert any("not found" in e for e in result["context_errors"])


def test_uses_canvas_session_from_state_directly(tmp_path: Path):
    node, _ = make_node(tmp_path)
    session = CanvasSessionState(
        session_id="injected",
        baseline_ref="baseline.prod",
        last_observed_graph_refresh=datetime.now(UTC),
    )
    state: AgentState = {"canvas_session": session}
    result = node(state)

    assert result["canvas_session"].session_id == "injected"


# ── Resolved graph ────────────────────────────────────────────────────────────

def test_resolved_graph_includes_baseline_nodes(tmp_path: Path):
    session, store = make_fresh_session(tmp_path)
    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "test-session"})
    ids = {n.id for n in result["resolved_graph"].nodes}
    assert "api" in ids and "db" in ids and "logger" in ids


def test_resolved_graph_applies_active_layers(tmp_path: Path):
    session, store = make_fresh_session(tmp_path)
    layer = SandboxLayer(
        id="layer-lambda",
        title="Add Lambda",
        added_nodes=[ComponentNode(id="lambda-fn", label="Lambda", tier="standard")],
        added_edges=[ComponentEdge(source_id="api", target_id="lambda-fn")],
    )
    session.add_layer(layer)
    session.activate_layer("layer-lambda")
    store.save(session)

    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "test-session"})
    ids = {n.id for n in result["resolved_graph"].nodes}
    assert "lambda-fn" in ids


# ── Freshness report ─────────────────────────────────────────────────────────

def test_fresh_data_final_forecast(tmp_path: Path):
    session, store = make_fresh_session(tmp_path)
    # last refresh 2h ago → fresh
    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "test-session"})
    assert result["freshness_report"].output_mode == OutputMode.FINAL_FORECAST


def test_never_refreshed_triggers_exploratory(tmp_path: Path):
    session = CanvasSessionState(
        session_id="stale-sess",
        baseline_ref="baseline.prod",
        last_observed_graph_refresh=None,   # never refreshed
    )
    store = SessionStore(base_dir=tmp_path / "sessions")
    store.save(session)

    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "stale-sess"})
    assert result["freshness_report"].output_mode == OutputMode.EXPLORATORY_ESTIMATE
    assert any("never been refreshed" in e for e in result["context_errors"])


def test_stale_data_adds_error(tmp_path: Path):
    session = CanvasSessionState(
        session_id="stale-sess2",
        baseline_ref="baseline.prod",
        last_observed_graph_refresh=datetime.now(UTC) - timedelta(hours=30),
    )
    store = SessionStore(base_dir=tmp_path / "sessions")
    store.save(session)

    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "stale-sess2"})
    assert any("Stale" in e for e in result["context_errors"])


# ── Calibration result ────────────────────────────────────────────────────────

def test_calibration_result_returned(tmp_path: Path):
    session, store = make_fresh_session(tmp_path)
    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "test-session", "proposal_id": "proposal.layer-lambda"})
    # No historical data → empty result, no buffer
    assert result["calibration_result"] is not None
    assert not result["calibration_result"].safety_buffer.applied


# ── Checkpoint restore ────────────────────────────────────────────────────────

def test_restores_from_pending_checkpoint(tmp_path: Path):
    session, store = make_fresh_session(tmp_path)
    layer = SandboxLayer(id="layer-a", title="A")
    session.add_layer(layer)
    session.activate_layer("layer-a")
    store.save(session)

    cp_store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    cp = CheckpointStore.create_from_session(
        session=session,
        pending_action="refresh_observed_graph",
        resume_node="ContextAndFreshnessNode",
    )
    cp_store.save(cp)

    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=cp_store,
    )
    result = node({"session_id": "test-session"})
    assert any("Restored from checkpoint" in e for e in result["context_errors"])
    assert "layer-a" in result["canvas_session"].active_layer_ids


# ── Optimization goal propagated ──────────────────────────────────────────────

def test_optimization_goal_propagated_from_session(tmp_path: Path):
    session = CanvasSessionState(
        session_id="goal-sess",
        baseline_ref="baseline.prod",
        optimization_goal=OptimizationGoal.MINIMAL_COMPLEXITY,
        last_observed_graph_refresh=datetime.now(UTC),
    )
    store = SessionStore(base_dir=tmp_path / "sessions")
    store.save(session)
    node = ContextAndFreshnessNode(
        session_store=store,
        checkpoint_store=CheckpointStore(tmp_path / "cp"),
    )
    result = node({"session_id": "goal-sess"})
    assert result["optimization_goal"] == OptimizationGoal.MINIMAL_COMPLEXITY
