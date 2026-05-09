from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.math_models.calibration_loop import (
    CalibrationLoopInput,
    CalibrationLoopOutput,
    SelfCalibrationLoop,
)

_loop = SelfCalibrationLoop()


class CalibrationAndBiasAdjustmentNode:
    """
    LangGraph node — runs the Self-Calibration Loop (Section 6.1).

    Derives metric_deltas from historical calibration errors already loaded
    into ``state["calibration_result"]`` by ContextAndFreshnessNode, then
    passes them to SelfCalibrationLoop to compute safety buffers and set
    actionable flags for downstream nodes.

    Reads:
        state["calibration_result"]   — CalibrationResult from ContextAndFreshnessNode
        state["source_component_id"]  — used to determine component_class
        state["resolved_graph"]       — source node's component_type → component_class

    Writes:
        state["calibration_loop_output"]  CalibrationLoopOutput
            .result.safety_buffer         applied multipliers (×1.15 if any delta >20%)
            .increase_blast_radius_depth  True when blast_radius historical delta >20%
            .human_review_required        True when security false negative detected
    """

    def __call__(self, state: AgentState) -> AgentState:
        source_id: str = state.get("source_component_id", "")
        resolved = state.get("resolved_graph")
        cal_result = state.get("calibration_result")

        # ── Derive component_class from source node ────────────────────────────
        component_class = "unknown"
        if resolved and source_id:
            src_node = resolved.get_node(source_id)
            if src_node and src_node.component_type:
                component_class = src_node.component_type

        # ── Extract metric_deltas from historical errors ───────────────────────
        # Take the worst-case (max) delta per metric across all CalibrationError
        # entries stored in calibration_result.historical_errors.
        metric_deltas: dict[str, float] = {}
        enabled = False

        if cal_result is not None:
            enabled = cal_result.enabled_for_existing_system
            for err in cal_result.historical_errors:
                if err.delta > metric_deltas.get(err.metric, 0.0):
                    metric_deltas[err.metric] = err.delta

        inp = CalibrationLoopInput(
            component_class=component_class,
            metric_deltas=metric_deltas,
            enabled_for_existing_system=enabled or bool(metric_deltas),
        )

        output: CalibrationLoopOutput = _loop.run(inp)
        return {**state, "calibration_loop_output": output}
