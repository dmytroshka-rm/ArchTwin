from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.calibration_store import CalibrationStore
from isa_cad.core.logging import get_logger

_log = get_logger(__name__)
from isa_cad.core.freshness_engine import FreshnessEngine, FreshnessReport
from isa_cad.core.models.calibration import CalibrationResult
from isa_cad.core.models.enums import OptimizationGoal
from isa_cad.core.models.freshness import DataSourceType
from isa_cad.state.canvas_state import CanvasSessionState, ComponentGraph
from isa_cad.state.checkpoint_store import CheckpointStore
from isa_cad.state.session_store import SessionStore


class ContextAndFreshnessNode:
    """
    LangGraph node — first in the workflow.

    Responsibilities (Section 0.2 + Section 4):
        1. Load baseline graph, sandbox layers, optimization goal, Canvas state
        2. Check data freshness for all sources
        3. Load historical calibration data for the component class
        4. Restore session from checkpoint if one exists

    Outputs written to AgentState:
        canvas_session, resolved_graph, freshness_report,
        calibration_result, context_ready, context_errors
    """

    def __init__(
        self,
        session_store: SessionStore | None = None,
        checkpoint_store: CheckpointStore | None = None,
        calibration_store: CalibrationStore | None = None,
        freshness_engine: FreshnessEngine | None = None,
    ) -> None:
        self._sessions     = session_store     or SessionStore()
        self._checkpoints  = checkpoint_store  or CheckpointStore()
        self._calibration  = calibration_store or CalibrationStore()
        self._freshness    = freshness_engine  or FreshnessEngine()

    # ── LangGraph entrypoint ──────────────────────────────────────────────────

    def __call__(self, state: AgentState) -> AgentState:
        session_id = state.get("session_id", "")
        _log.info("node.start", node="context_freshness", session_id=session_id)
        errors: list[str] = []

        session = self._load_session(state, errors)
        session = self._maybe_restore_from_checkpoint(session, state, errors)
        resolved_graph = session.resolved_graph()

        freshness_report = self._check_freshness(session, errors)
        calibration_result = self._load_calibration(state, errors)

        _log.info(
            "node.done",
            node="context_freshness",
            session_id=session_id,
            context_ready=(len(errors) == 0),
            errors=errors or None,
            graph_nodes=len(resolved_graph.nodes),
        )
        return {
            **state,
            "canvas_session":     session,
            "resolved_graph":     resolved_graph,
            "freshness_report":   freshness_report,
            "calibration_result": calibration_result,
            "optimization_goal":  session.optimization_goal,
            "context_ready":      len(errors) == 0,
            "context_errors":     errors,
        }

    # ── private helpers ───────────────────────────────────────────────────────

    def _load_session(
        self,
        state: AgentState,
        errors: list[str],
    ) -> CanvasSessionState:
        """
        Load existing session from store, or create a fresh one from state inputs.
        """
        session_id = state.get("session_id", "")

        if session_id:
            existing = self._sessions.load(session_id)
            if existing:
                return existing

        # Build a minimal session from state inputs
        session_id = session_id or f"session.{datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}"
        session = CanvasSessionState(
            session_id=session_id,
            baseline_ref=state.get("baseline_ref", "architecture.baseline.unknown"),
            optimization_goal=state.get("optimization_goal", OptimizationGoal.BALANCED),
        )

        # If a canvas_session was already set on state (e.g. from test setup), use it
        if existing_session := state.get("canvas_session"):
            return existing_session

        errors.append(
            f"Session '{session_id}' not found in store — created empty session. "
            "Provide a pre-loaded CanvasSessionState for full analysis."
        )
        return session

    def _maybe_restore_from_checkpoint(
        self,
        session: CanvasSessionState,
        state: AgentState,
        errors: list[str],
    ) -> CanvasSessionState:
        """
        If there is an unresolved checkpoint for this session, restore state from it.
        """
        checkpoints = self._checkpoints.load_all_for_session(session.session_id)
        pending = [cp for cp in checkpoints if not cp.resumed]
        if not pending:
            return session

        latest = pending[-1]
        session = CheckpointStore.restore_session(session, latest)
        errors.append(
            f"Restored from checkpoint '{latest.id}' "
            f"(pending_action='{latest.pending_action}', "
            f"resume_node='{latest.resume_node}')."
        )
        return session

    def _check_freshness(
        self,
        session: CanvasSessionState,
        errors: list[str],
    ) -> FreshnessReport:
        """
        Analyse data freshness. Uses last_observed_graph_refresh as proxy
        for cloud_inventory and runtime_metrics age.
        """
        now = datetime.now(UTC)
        collected_at_map: dict[DataSourceType, datetime] = {}

        if session.last_observed_graph_refresh:
            collected_at_map[DataSourceType.CLOUD_INVENTORY] = (
                session.last_observed_graph_refresh
            )
            collected_at_map[DataSourceType.RUNTIME_METRICS] = (
                session.last_observed_graph_refresh
            )
        else:
            # No refresh recorded — treat as very stale (force exploratory mode)
            stale_ts = now - timedelta(days=8)
            collected_at_map[DataSourceType.CLOUD_INVENTORY] = stale_ts
            collected_at_map[DataSourceType.RUNTIME_METRICS] = stale_ts
            errors.append(
                "Observed graph has never been refreshed. "
                "All outputs will be Exploratory Estimates."
            )

        report = self._freshness.analyse(
            collected_at_map,
            base_confidence=1.0,
            now=now,
        )

        if report.require_observed_graph_refresh:
            errors.append(
                f"Adjusted confidence {report.adjusted_confidence:.2f} < minimum. "
                "Observed Graph refresh required before final forecast."
            )

        if report.stale_sources:
            errors.append(
                f"Stale data sources: {', '.join(report.stale_sources)}."
            )

        return report

    def _load_calibration(
        self,
        state: AgentState,
        errors: list[str],
    ) -> CalibrationResult:
        """
        Load historical calibration data for the component class inferred
        from the proposal, or return an empty result if none available.
        """
        proposal_id = state.get("proposal_id", "")
        # Infer component class from proposal_id heuristic
        component_class = _infer_component_class(proposal_id)

        result = self._calibration.build_calibration_result(component_class)

        if result.safety_buffer.applied:
            errors.append(
                f"Safety buffer active for component class '{component_class}': "
                f"{result.safety_buffer.reason}"
            )

        return result


# ── helpers ───────────────────────────────────────────────────────────────────

_COMPONENT_CLASS_KEYWORDS = {
    "lambda":    ["lambda", "serverless", "function"],
    "ecs":       ["ecs", "fargate", "container"],
    "rds":       ["rds", "postgresql", "mysql", "aurora", "database", "db"],
    "redis":     ["redis", "elasticache", "cache"],
    "sqs":       ["sqs", "queue", "sns"],
    "api-gw":    ["api-gw", "apigateway", "gateway"],
    "s3":        ["s3", "storage", "bucket"],
}


def _infer_component_class(proposal_id: str) -> str:
    lower = proposal_id.lower()
    for cc, keywords in _COMPONENT_CLASS_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return cc
    return "unknown"
