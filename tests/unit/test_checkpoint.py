from __future__ import annotations

from pathlib import Path

import pytest

from isa_cad.core.models.checkpoint import Checkpoint, PartialReviewerOutput
from isa_cad.core.models.enums import OptimizationGoal
from isa_cad.state.canvas_state import CanvasSessionState, SandboxLayer
from isa_cad.state.checkpoint_store import CheckpointStore


# ── helpers ──────────────────────────────────────────────────────────────────

def make_session(sid: str = "session-001") -> CanvasSessionState:
    s = CanvasSessionState(session_id=sid, baseline_ref="baseline.prod")
    s.optimization_goal = OptimizationGoal.COST_EFFICIENCY
    s.assumptions = ["CDN CHR = 0.85 assumed"]
    s.add_layer(SandboxLayer(id="layer-a", title="Serverless"))
    s.add_layer(SandboxLayer(id="layer-b", title="Managed ECS"))
    s.activate_layer("layer-a")
    return s


def make_partial_outputs() -> list[PartialReviewerOutput]:
    return [
        PartialReviewerOutput(
            node_name="CostReviewerNode",
            is_complete=True,
            payload={"monthly_projected_usd": 850},
        ),
        PartialReviewerOutput(
            node_name="PerformanceReviewerNode",
            is_complete=False,
            payload={"latency_delta": "pending"},
        ),
    ]


# ── Checkpoint model ─────────────────────────────────────────────────────────

def test_checkpoint_empty_id_raises():
    with pytest.raises(ValueError, match="not be empty"):
        Checkpoint(id="  ", baseline_ref="baseline.prod")


def test_checkpoint_get_output_found():
    outputs = make_partial_outputs()
    cp = Checkpoint(id="cp-001", baseline_ref="baseline.prod", preserved_outputs=outputs)
    out = cp.get_output("CostReviewerNode")
    assert out is not None
    assert out.payload["monthly_projected_usd"] == 850


def test_checkpoint_get_output_not_found():
    cp = Checkpoint(id="cp-002", baseline_ref="baseline.prod")
    assert cp.get_output("SecurityReviewerNode") is None


def test_checkpoint_complete_and_partial_node_names():
    outputs = make_partial_outputs()
    cp = Checkpoint(id="cp-003", baseline_ref="baseline.prod", preserved_outputs=outputs)
    assert "CostReviewerNode" in cp.complete_node_names
    assert "PerformanceReviewerNode" in cp.partial_node_names


def test_checkpoint_mark_resumed():
    cp = Checkpoint(id="cp-004", baseline_ref="baseline.prod")
    assert not cp.resumed
    cp.mark_resumed()
    assert cp.resumed
    assert cp.resumed_at is not None


# ── CheckpointStore ───────────────────────────────────────────────────────────

def test_create_from_session():
    session = make_session()
    cp = CheckpointStore.create_from_session(
        session=session,
        pending_action="refresh_observed_graph",
        resume_node="ContextAndFreshnessNode",
        partial_outputs=make_partial_outputs(),
    )
    assert cp.canvas_session_id == "session-001"
    assert cp.baseline_ref == "baseline.prod"
    assert cp.optimization_goal == OptimizationGoal.COST_EFFICIENCY
    assert cp.pending_action == "refresh_observed_graph"
    assert cp.resume_node == "ContextAndFreshnessNode"
    assert "layer-a" in cp.sandbox_layer_ids
    assert "layer-b" not in cp.sandbox_layer_ids  # only active layers
    assert cp.assumptions == ["CDN CHR = 0.85 assumed"]
    assert len(cp.preserved_outputs) == 2


def test_save_and_load(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    session = make_session()
    cp = CheckpointStore.create_from_session(
        session=session,
        pending_action="refresh_observed_graph",
        partial_outputs=make_partial_outputs(),
    )
    store.save(cp)
    loaded = store.load(cp.id)
    assert loaded is not None
    assert loaded.id == cp.id
    assert loaded.optimization_goal == cp.optimization_goal
    assert len(loaded.preserved_outputs) == 2
    assert loaded.get_output("CostReviewerNode") is not None


def test_load_nonexistent_returns_none(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    assert store.load("ghost-checkpoint") is None


def test_delete_checkpoint(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    session = make_session()
    cp = CheckpointStore.create_from_session(session, "refresh")
    store.save(cp)
    assert store.delete(cp.id) is True
    assert store.load(cp.id) is None


def test_delete_nonexistent(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    assert store.delete("ghost") is False


def test_list_checkpoints(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    s1 = make_session("s1")
    s2 = make_session("s2")
    cp1 = CheckpointStore.create_from_session(s1, "refresh")
    cp2 = CheckpointStore.create_from_session(s2, "refresh")
    store.save(cp1)
    store.save(cp2)
    ids = store.list_checkpoints()
    assert len(ids) == 2


def test_load_all_for_session(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    session = make_session("multi-cp-session")
    cp1 = CheckpointStore.create_from_session(session, "refresh")
    cp2 = CheckpointStore.create_from_session(session, "await_pricing")
    store.save(cp1)
    store.save(cp2)
    all_cp = store.load_all_for_session("multi-cp-session")
    assert len(all_cp) == 2
    # Should be sorted by saved_at
    assert all_cp[0].saved_at <= all_cp[1].saved_at


def test_restore_session(tmp_path: Path):
    store = CheckpointStore(base_dir=tmp_path)
    session = make_session()
    partial = make_partial_outputs()
    cp = CheckpointStore.create_from_session(session, "refresh", partial_outputs=partial)
    store.save(cp)

    # Simulate a fresh session (e.g. after process restart)
    fresh_session = CanvasSessionState(
        session_id="session-001",
        baseline_ref="baseline.prod",
    )
    fresh_session.add_layer(SandboxLayer(id="layer-a", title="Serverless"))
    fresh_session.add_layer(SandboxLayer(id="layer-b", title="Managed ECS"))

    loaded_cp = store.load(cp.id)
    restored = CheckpointStore.restore_session(fresh_session, loaded_cp)

    assert restored.optimization_goal == OptimizationGoal.COST_EFFICIENCY
    assert "layer-a" in restored.active_layer_ids
    assert "layer-b" not in restored.active_layer_ids
    assert restored.assumptions == ["CDN CHR = 0.85 assumed"]
    assert "CostReviewerNode" in restored.partial_outputs
    assert loaded_cp.resumed is True
