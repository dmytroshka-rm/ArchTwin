from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.checkpoint import Checkpoint, PartialReviewerOutput
from isa_cad.state.canvas_state import CanvasSessionState
from isa_cad.state.checkpoint_store import CheckpointStore


# Reviewer state keys and the node names they correspond to
_REVIEWER_KEYS: dict[str, str] = {
    "cost_review":        "CostReviewerNode",
    "performance_review": "PerformanceReviewerNode",
    "security_review":    "SecurityReviewerNode",
}


def _collect_partial_outputs(state: AgentState) -> list[PartialReviewerOutput]:
    """
    Capture reviewer outputs from state as PartialReviewerOutput entries.
    Only includes reviewers that are present (completed at least partially).
    """
    outputs: list[PartialReviewerOutput] = []
    for key, node_name in _REVIEWER_KEYS.items():
        review = state.get(key)  # type: ignore[literal-required]
        if review is None:
            continue
        try:
            payload = review.model_dump()
        except AttributeError:
            payload = dict(review) if isinstance(review, dict) else {}
        outputs.append(PartialReviewerOutput(
            node_name=node_name,
            is_complete=True,
            payload=payload,
        ))
    return outputs


class StatePersistenceNode:
    """
    LangGraph node — persists a Checkpoint before any async wait
    (e.g. Observed Graph refresh, pricing update).
    Section 6.2 of the convention.

    The checkpoint captures everything needed to resume analysis without
    re-running completed upstream nodes:
      - CanvasSession identity (session_id, baseline_ref, sandbox layers)
      - Completed reviewer outputs (cost, performance, security)
      - Assumptions collected during this run
      - Which node to resume from (always ContextAndFreshnessNode for a refresh)

    Reads:
        state["checkpoint_required"]   — True → create & save checkpoint
        state["canvas_session"]        — source of session identity data
        state["cost_review"]           — preserved if present (optional)
        state["performance_review"]    — preserved if present (optional)
        state["security_review"]       — preserved if present (optional)

    Writes:
        state["checkpoint"]            Checkpoint | None
        state["checkpoint_required"]   always False after this node
    """

    def __init__(self, store: CheckpointStore | None = None) -> None:
        self._store = store  # None → lazy-create default store on first save

    def _get_store(self) -> CheckpointStore:
        if self._store is None:
            self._store = CheckpointStore()
        return self._store

    def __call__(self, state: AgentState) -> AgentState:
        required: bool = state.get("checkpoint_required", False)
        session: CanvasSessionState | None = state.get("canvas_session")

        if not required or session is None:
            return {**state, "checkpoint": None, "checkpoint_required": False}

        partial_outputs = _collect_partial_outputs(state)

        pending_action = (
            "refresh_observed_graph"
            if session.observed_graph_stale
            else "await_resume"
        )

        checkpoint = CheckpointStore.create_from_session(
            session=session,
            pending_action=pending_action,
            resume_node="ContextAndFreshnessNode",
            partial_outputs=partial_outputs,
        )

        self._get_store().save(checkpoint)

        return {**state, "checkpoint": checkpoint, "checkpoint_required": False}
