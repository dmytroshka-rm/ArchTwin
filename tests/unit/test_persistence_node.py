from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.persistence import StatePersistenceNode
from isa_cad.core.models.checkpoint import Checkpoint
from isa_cad.core.models.enums import OptimizationGoal, ReviewerStatus
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.state.canvas_state import CanvasSessionState, ComponentGraph, ComponentNode
from isa_cad.state.checkpoint_store import CheckpointStore


# ── helpers ───────────────────────────────────────────────────────────────────

def make_session(
    session_id: str = "sess-1",
    baseline_ref: str = "arch.baseline.prod",
    stale: bool = False,
    goal: OptimizationGoal = OptimizationGoal.BALANCED,
) -> CanvasSessionState:
    s = CanvasSessionState(session_id=session_id, baseline_ref=baseline_ref)
    s.optimization_goal = goal
    if stale:
        s.mark_stale()
    return s


def make_node(tmp_path) -> StatePersistenceNode:
    store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    return StatePersistenceNode(store=store)


def reviewer(cls, status=ReviewerStatus.PASS, score=0.8):
    return cls(status=status, score=score, confidence=0.7, recommendation="ok")


# ── Output contract ───────────────────────────────────────────────────────────

def test_checkpoint_key_always_present(tmp_path):
    node = make_node(tmp_path)
    result = node({"checkpoint_required": False})
    assert "checkpoint" in result


def test_checkpoint_required_reset_to_false(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    state: AgentState = {
        "checkpoint_required": True,
        "canvas_session": sess,
    }
    result = node(state)
    assert result["checkpoint_required"] is False


def test_checkpoint_required_false_stays_false(tmp_path):
    node = make_node(tmp_path)
    result = node({"checkpoint_required": False})
    assert result["checkpoint_required"] is False


# ── Skip conditions ───────────────────────────────────────────────────────────

def test_checkpoint_required_false_returns_none(tmp_path):
    node = make_node(tmp_path)
    result = node({"checkpoint_required": False, "canvas_session": make_session()})
    assert result["checkpoint"] is None


def test_no_session_returns_none(tmp_path):
    node = make_node(tmp_path)
    result = node({"checkpoint_required": True})
    assert result["checkpoint"] is None


def test_no_session_no_save(tmp_path):
    store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    node = StatePersistenceNode(store=store)
    node({"checkpoint_required": True})
    assert store.list_checkpoints() == []


def test_not_required_no_save(tmp_path):
    store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    node = StatePersistenceNode(store=store)
    node({"checkpoint_required": False, "canvas_session": make_session()})
    assert store.list_checkpoints() == []


# ── Checkpoint creation ───────────────────────────────────────────────────────

def test_checkpoint_is_checkpoint_instance(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert isinstance(result["checkpoint"], Checkpoint)


def test_checkpoint_session_id_matches(tmp_path):
    node = make_node(tmp_path)
    sess = make_session(session_id="my-session")
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"].canvas_session_id == "my-session"


def test_checkpoint_baseline_ref_matches(tmp_path):
    node = make_node(tmp_path)
    sess = make_session(baseline_ref="arch.v2.prod")
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"].baseline_ref == "arch.v2.prod"


def test_checkpoint_resume_node_is_context_freshness(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"].resume_node == "ContextAndFreshnessNode"


def test_checkpoint_optimization_goal_propagated(tmp_path):
    node = make_node(tmp_path)
    sess = make_session(goal=OptimizationGoal.COST_EFFICIENCY)
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"].optimization_goal == OptimizationGoal.COST_EFFICIENCY


# ── pending_action from observed_graph_stale ─────────────────────────────────

def test_stale_session_pending_action_is_refresh(tmp_path):
    node = make_node(tmp_path)
    sess = make_session(stale=True)
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"].pending_action == "refresh_observed_graph"


def test_fresh_session_pending_action_is_await_resume(tmp_path):
    node = make_node(tmp_path)
    sess = make_session(stale=False)
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"].pending_action == "await_resume"


# ── Checkpoint persisted to store ─────────────────────────────────────────────

def test_checkpoint_saved_to_store(tmp_path):
    store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    node = StatePersistenceNode(store=store)
    sess = make_session()
    result = node({"checkpoint_required": True, "canvas_session": sess})
    cp_id = result["checkpoint"].id
    loaded = store.load(cp_id)
    assert loaded is not None
    assert loaded.id == cp_id


def test_saved_checkpoint_has_correct_session_id(tmp_path):
    store = CheckpointStore(base_dir=tmp_path / "checkpoints")
    node = StatePersistenceNode(store=store)
    sess = make_session(session_id="reload-test")
    result = node({"checkpoint_required": True, "canvas_session": sess})
    loaded = store.load(result["checkpoint"].id)
    assert loaded.canvas_session_id == "reload-test"


# ── Partial reviewer outputs preserved ───────────────────────────────────────

def test_cost_review_preserved_in_checkpoint(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    state: AgentState = {
        "checkpoint_required": True,
        "canvas_session": sess,
        "cost_review": reviewer(CostReviewerOutput),
    }
    result = node(state)
    cp = result["checkpoint"]
    cost_out = cp.get_output("CostReviewerNode")
    assert cost_out is not None
    assert cost_out.is_complete is True


def test_all_three_reviewers_preserved(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    state: AgentState = {
        "checkpoint_required": True,
        "canvas_session": sess,
        "cost_review":        reviewer(CostReviewerOutput),
        "performance_review": reviewer(PerformanceReviewerOutput),
        "security_review":    reviewer(SecurityReviewerOutput),
    }
    result = node(state)
    cp = result["checkpoint"]
    node_names = {o.node_name for o in cp.preserved_outputs}
    assert "CostReviewerNode" in node_names
    assert "PerformanceReviewerNode" in node_names
    assert "SecurityReviewerNode" in node_names


def test_missing_reviewers_not_preserved(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    # Only cost_review in state
    state: AgentState = {
        "checkpoint_required": True,
        "canvas_session": sess,
        "cost_review": reviewer(CostReviewerOutput),
    }
    result = node(state)
    cp = result["checkpoint"]
    assert cp.get_output("PerformanceReviewerNode") is None
    assert cp.get_output("SecurityReviewerNode") is None


def test_no_reviewers_checkpoint_still_created(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    result = node({"checkpoint_required": True, "canvas_session": sess})
    assert result["checkpoint"] is not None
    assert result["checkpoint"].preserved_outputs == []


# ── State passthrough ─────────────────────────────────────────────────────────

def test_existing_state_keys_preserved(tmp_path):
    node = make_node(tmp_path)
    sess = make_session()
    state: AgentState = {
        "checkpoint_required": True,
        "canvas_session": sess,
        "session_id": "outer-sess",
    }
    result = node(state)
    assert result["session_id"] == "outer-sess"
    assert "checkpoint" in result


def test_passthrough_when_skipped(tmp_path):
    node = make_node(tmp_path)
    state: AgentState = {
        "checkpoint_required": False,
        "session_id": "passthrough-test",
    }
    result = node(state)
    assert result["session_id"] == "passthrough-test"
