from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes.calibration import CalibrationAndBiasAdjustmentNode
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput
from isa_cad.core.models.calibration import CalibrationError, CalibrationResult
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
)

node = CalibrationAndBiasAdjustmentNode()


# ── helpers ───────────────────────────────────────────────────────────────────

def n(nid: str, ctype: str = "service") -> ComponentNode:
    return ComponentNode(id=nid, label=nid, tier="standard", component_type=ctype)


def simple_graph(source_id: str, ctype: str = "service") -> ComponentGraph:
    return ComponentGraph(nodes=[n(source_id, ctype)], edges=[])


def cal_result_with(*metrics_deltas: tuple[str, float]) -> CalibrationResult:
    errors = [
        CalibrationError(
            metric=m,
            predicted_value=round(1.0 + d, 6),
            actual_value=1.0,
        )
        for m, d in metrics_deltas
    ]
    return CalibrationResult(
        enabled_for_existing_system=True,
        historical_errors=errors,
    )


def run(
    source_id: str = "svc",
    graph: ComponentGraph | None = None,
    cal_result: CalibrationResult | None = None,
    extra: dict | None = None,
) -> dict:
    state: AgentState = {"source_component_id": source_id}
    if graph is not None:
        state["resolved_graph"] = graph
    if cal_result is not None:
        state["calibration_result"] = cal_result
    if extra:
        state.update(extra)
    return node(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_key_present():
    result = run()
    assert "calibration_loop_output" in result
    assert isinstance(result["calibration_loop_output"], CalibrationLoopOutput)


def test_output_has_result():
    result = run()
    assert result["calibration_loop_output"].result is not None


def test_state_passthrough():
    result = run(extra={"session_id": "sess-cal"})
    assert result["session_id"] == "sess-cal"
    assert "calibration_loop_output" in result


# ── component_class derivation ────────────────────────────────────────────────

def test_component_class_from_source_node():
    g = simple_graph("api", "gateway")
    result = run("api", g)
    out = result["calibration_loop_output"]
    # loop was run for "gateway" component class (summary contains component class)
    assert "gateway" in out.summary


def test_component_class_unknown_when_no_graph():
    result = run("api", graph=None)
    out = result["calibration_loop_output"]
    assert "unknown" in out.summary


def test_component_class_unknown_when_source_not_in_graph():
    g = simple_graph("other", "database")
    result = run("api", g)
    out = result["calibration_loop_output"]
    assert "unknown" in out.summary


# ── No calibration data ───────────────────────────────────────────────────────

def test_no_cal_result_no_buffer():
    result = run(cal_result=None)
    out = result["calibration_loop_output"]
    assert not out.result.safety_buffer.applied


def test_no_cal_result_no_increase_depth():
    result = run(cal_result=None)
    assert not result["calibration_loop_output"].increase_blast_radius_depth


def test_no_cal_result_no_human_review():
    result = run(cal_result=None)
    assert not result["calibration_loop_output"].human_review_required


# ── Metric delta extraction from CalibrationResult ───────────────────────────

def test_cost_delta_above_threshold_applies_buffer():
    cr = cal_result_with(("cost", 0.25))
    result = run(cal_result=cr)
    out = result["calibration_loop_output"]
    assert out.result.safety_buffer.applied
    assert out.result.safety_buffer.cost_multiplier == pytest.approx(1.15)


def test_latency_delta_above_threshold_applies_buffer():
    cr = cal_result_with(("latency", 0.22))
    result = run(cal_result=cr)
    out = result["calibration_loop_output"]
    assert out.result.safety_buffer.applied
    assert out.result.safety_buffer.latency_multiplier == pytest.approx(1.15)


def test_cost_below_threshold_no_buffer():
    cr = cal_result_with(("cost", 0.10))
    result = run(cal_result=cr)
    assert not result["calibration_loop_output"].result.safety_buffer.applied


def test_worst_case_delta_used_when_multiple_cost_errors():
    """Two cost errors — only the worst one should determine the buffer."""
    cr = CalibrationResult(
        enabled_for_existing_system=True,
        historical_errors=[
            CalibrationError(metric="cost", predicted_value=1.10, actual_value=1.0),  # delta=0.10
            CalibrationError(metric="cost", predicted_value=1.30, actual_value=1.0),  # delta=0.30
        ],
    )
    result = run(cal_result=cr)
    out = result["calibration_loop_output"]
    # worst = 0.30 > 0.20 → buffer applied
    assert out.result.safety_buffer.applied


# ── increase_blast_radius_depth flag ─────────────────────────────────────────

def test_blast_radius_delta_above_threshold_sets_increase_depth():
    cr = cal_result_with(("blast_radius", 0.25))
    result = run(cal_result=cr)
    assert result["calibration_loop_output"].increase_blast_radius_depth is True


def test_blast_radius_delta_below_threshold_no_increase_depth():
    cr = cal_result_with(("blast_radius", 0.15))
    result = run(cal_result=cr)
    assert result["calibration_loop_output"].increase_blast_radius_depth is False


def test_blast_radius_exactly_threshold_no_increase_depth():
    # strictly > 0.20; exactly 0.20 does NOT trigger
    cr = cal_result_with(("blast_radius", 0.20))
    result = run(cal_result=cr)
    assert result["calibration_loop_output"].increase_blast_radius_depth is False


# ── human_review_required flag ────────────────────────────────────────────────

def test_security_false_negative_sets_human_review():
    cr = cal_result_with(("security_false_negative", 1.0))
    result = run(cal_result=cr)
    assert result["calibration_loop_output"].human_review_required is True


def test_security_false_negative_zero_no_human_review():
    cr = cal_result_with(("security_false_negative", 0.0))
    result = run(cal_result=cr)
    assert result["calibration_loop_output"].human_review_required is False


def test_no_security_false_negative_no_human_review():
    cr = cal_result_with(("cost", 0.25))
    result = run(cal_result=cr)
    assert result["calibration_loop_output"].human_review_required is False


# ── All signals at once ───────────────────────────────────────────────────────

def test_all_signals_all_flags_set():
    cr = cal_result_with(
        ("cost", 0.25),
        ("latency", 0.22),
        ("security_false_negative", 1.0),
        ("blast_radius", 0.30),
    )
    g = simple_graph("lambda", "lambda")
    result = run("lambda", g, cr)
    out = result["calibration_loop_output"]
    assert out.result.safety_buffer.applied
    assert out.increase_blast_radius_depth is True
    assert out.human_review_required is True
    assert len(out.signal_actions) == 4


# ── Summary ───────────────────────────────────────────────────────────────────

def test_summary_present():
    result = run()
    assert result["calibration_loop_output"].summary != ""


def test_summary_contains_component_class():
    g = simple_graph("db", "database")
    result = run("db", g)
    assert "database" in result["calibration_loop_output"].summary


def test_summary_no_buffer_when_no_signal():
    cr = cal_result_with(("cost", 0.05))
    result = run(cal_result=cr)
    assert "No safety buffer" in result["calibration_loop_output"].summary


# ── enabled_for_existing_system propagation ───────────────────────────────────

def test_disabled_cal_result_skipped_in_summary():
    cr = CalibrationResult(
        enabled_for_existing_system=False,
        historical_errors=[],
    )
    result = run(cal_result=cr)
    out = result["calibration_loop_output"]
    assert "skipped" in out.summary.lower()
