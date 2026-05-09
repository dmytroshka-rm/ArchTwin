from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.math_models.blast_radius import BlastRadiusCalculator, BlastRadiusInput
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.state.canvas_state import ComponentGraph


_calculator = BlastRadiusCalculator()

# Maximum BFS depth when no proposal overrides it
_DEFAULT_MAX_DEPTH = 3


def _empty_output(source_id: str, reason: str) -> BlastRadiusOutput:
    return BlastRadiusOutput(
        source_component_id=source_id or "unknown",
        max_traversal_depth=_DEFAULT_MAX_DEPTH,
        impacted_stable_components=[],
        summary=reason,
    )


class BlastRadiusNode:
    """
    LangGraph node — computes tier-aware blast radius from the modified
    component outward through the resolved graph.

    Formula (Section 3.3):
        impact_score = (base_impact * C_m) * 0.5 ** (d − 1)

    Where:
        d   = BFS graph distance from source_component_id
        C_m = TIER_1→2.0, STANDARD→1.0, AUXILIARY→0.5
        base_impact = 1.0 (default; can be overridden via proposal metadata)

    Reads:
        state["source_component_id"]   — from BuildDesignDeltaNode
        state["resolved_graph"]        — from ContextAndFreshnessNode
        state["canvas_session"]        — for baseline comparison (optional)
        state["proposal"]              — for max_depth override (optional)

    Writes:
        state["blast_radius"]          BlastRadiusOutput
    """

    def __call__(self, state: AgentState) -> AgentState:
        source_id: str         = state.get("source_component_id", "")
        resolved: ComponentGraph | None = state.get("resolved_graph")

        if not source_id:
            output = _empty_output("", "No source_component_id in state — blast radius skipped.")
            return {**state, "blast_radius": output}

        if resolved is None:
            output = _empty_output(source_id, "No resolved_graph in state — blast radius skipped.")
            return {**state, "blast_radius": output}

        # Verify source node exists in graph
        if resolved.get_node(source_id) is None:
            output = _empty_output(
                source_id,
                f"Source component '{source_id}' not found in resolved graph — "
                "blast radius skipped.",
            )
            return {**state, "blast_radius": output}

        # Optional max_depth override from proposal metadata
        max_depth = _DEFAULT_MAX_DEPTH
        proposal = state.get("proposal")
        if proposal and hasattr(proposal, "scoring"):
            # Check if the calibration loop recommended deeper traversal
            cal_output = state.get("calibration_loop_output")
            if cal_output and getattr(cal_output, "increase_blast_radius_depth", False):
                max_depth = _DEFAULT_MAX_DEPTH + 1

        inp = BlastRadiusInput(
            source_component_id=source_id,
            graph=resolved,
            max_depth=max_depth,
            base_impact=1.0,
        )

        output = _calculator.compute(inp)

        # Attach baseline diff if baseline graph available
        baseline_diff: dict | None = None
        session = state.get("canvas_session")
        if session and session.baseline_graph:
            baseline_inp = BlastRadiusInput(
                source_component_id=source_id,
                graph=session.baseline_graph,
                max_depth=max_depth,
                base_impact=1.0,
            )
            # Source may not exist in baseline (newly added node) — handle gracefully
            if session.baseline_graph.get_node(source_id) is not None:
                baseline_output = _calculator.compute(baseline_inp)
                baseline_diff = _calculator.diff(baseline_output, output)

        result_state = {**state, "blast_radius": output}
        if baseline_diff is not None:
            result_state["blast_radius_diff"] = baseline_diff

        return result_state
