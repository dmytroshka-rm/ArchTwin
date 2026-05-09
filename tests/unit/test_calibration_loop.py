from __future__ import annotations

import pytest

from isa_cad.core.math_models.calibration_loop import (
    CalibrationLoopInput,
    SelfCalibrationLoop,
)
from isa_cad.core.models.calibration_record import ActualRecord, CalibrationEntry, ForecastRecord

loop = SelfCalibrationLoop()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_entry(metric: str, predicted: float, actual: float) -> CalibrationEntry:
    f = ForecastRecord(
        id=f"f-{metric}-{predicted}",
        proposal_id="proposal.test",
        component_class="lambda",
        metric=metric,
        predicted_value=predicted,
    )
    a = ActualRecord(forecast_id=f.id, actual_value=actual)
    return CalibrationEntry(forecast=f, actual=a)


# ── No historical data ────────────────────────────────────────────────────────

def test_no_data_no_buffer():
    out = loop.run(CalibrationLoopInput(
        component_class="lambda",
        metric_deltas={},
        enabled_for_existing_system=False,
    ))
    assert not out.result.safety_buffer.applied
    assert "skipped" in out.summary


def test_empty_deltas_no_buffer():
    out = loop.run(CalibrationLoopInput(
        component_class="ecs",
        metric_deltas={"cost": 0.0, "latency": 0.0},
    ))
    assert not out.result.safety_buffer.applied
    assert out.signal_actions == {}


# ── Cost buffer ───────────────────────────────────────────────────────────────

def test_cost_delta_below_threshold_no_buffer():
    # 0.15 < 0.20 → no buffer
    out = loop.run(CalibrationLoopInput("lambda", {"cost": 0.15}))
    assert not out.result.safety_buffer.applied
    assert "cost" not in out.signal_actions


def test_cost_delta_exactly_threshold_no_buffer():
    # 0.20 is NOT > 0.20 → no buffer (strictly greater)
    out = loop.run(CalibrationLoopInput("lambda", {"cost": 0.20}))
    assert not out.result.safety_buffer.applied


def test_cost_delta_above_threshold_buffer_applied():
    out = loop.run(CalibrationLoopInput("lambda", {"cost": 0.24}))
    assert out.result.safety_buffer.applied
    assert out.result.safety_buffer.cost_multiplier == pytest.approx(1.15)
    assert out.result.safety_buffer.latency_multiplier == pytest.approx(1.0)
    assert "cost" in out.signal_actions
    assert "15%" in out.signal_actions["cost"]
    assert "lambda" in out.signal_actions["cost"]


def test_cost_buffer_bias_note_populated():
    out = loop.run(CalibrationLoopInput("ecs", {"cost": 0.30}))
    assert out.result.safety_buffer.bias_note is not None
    assert "15%" in out.result.safety_buffer.bias_note


# ── Latency buffer ────────────────────────────────────────────────────────────

def test_latency_delta_above_threshold_buffer_applied():
    out = loop.run(CalibrationLoopInput("rds", {"latency": 0.25}))
    assert out.result.safety_buffer.applied
    assert out.result.safety_buffer.latency_multiplier == pytest.approx(1.15)
    assert out.result.safety_buffer.cost_multiplier == pytest.approx(1.0)
    assert "latency" in out.signal_actions


# ── Both cost + latency ───────────────────────────────────────────────────────

def test_both_cost_and_latency_exceed_threshold():
    out = loop.run(CalibrationLoopInput("lambda", {"cost": 0.24, "latency": 0.21}))
    assert out.result.safety_buffer.applied
    assert out.result.safety_buffer.cost_multiplier    == pytest.approx(1.15)
    assert out.result.safety_buffer.latency_multiplier == pytest.approx(1.15)
    assert "cost" in out.signal_actions
    assert "latency" in out.signal_actions


# ── Security false negative ───────────────────────────────────────────────────

def test_security_false_negative_action_raised():
    out = loop.run(CalibrationLoopInput("api-gw", {"security_false_negative": 1.0}))
    assert "security_false_negative" in out.signal_actions
    assert "human review" in out.signal_actions["security_false_negative"].lower()


def test_security_false_negative_zero_no_action():
    out = loop.run(CalibrationLoopInput("api-gw", {"security_false_negative": 0.0}))
    assert "security_false_negative" not in out.signal_actions


# ── Blast radius underestimation ──────────────────────────────────────────────

def test_blast_radius_above_threshold_action_raised():
    out = loop.run(CalibrationLoopInput("ecs", {"blast_radius": 0.30}))
    assert "blast_radius" in out.signal_actions
    assert "traversal" in out.signal_actions["blast_radius"].lower()


def test_blast_radius_below_threshold_no_action():
    out = loop.run(CalibrationLoopInput("ecs", {"blast_radius": 0.10}))
    assert "blast_radius" not in out.signal_actions


# ── All four signals at once ──────────────────────────────────────────────────

def test_all_signals_active():
    out = loop.run(CalibrationLoopInput("svc", {
        "cost":                   0.30,
        "latency":                0.25,
        "security_false_negative": 1.0,
        "blast_radius":           0.22,
    }))
    assert out.result.safety_buffer.applied
    assert len(out.signal_actions) == 4
    assert len(out.result.calibration_notes) == 4


# ── Calibration notes in result ───────────────────────────────────────────────

def test_calibration_notes_populated():
    out = loop.run(CalibrationLoopInput("lambda", {"cost": 0.24, "latency": 0.21}))
    assert len(out.result.calibration_notes) >= 2
    joined = " ".join(out.result.calibration_notes)
    assert "safety buffer" in joined.lower()


# ── Summary ───────────────────────────────────────────────────────────────────

def test_summary_contains_component_class():
    out = loop.run(CalibrationLoopInput("my-svc", {"cost": 0.25}))
    assert "my-svc" in out.summary


def test_summary_no_buffer_message():
    out = loop.run(CalibrationLoopInput("svc", {"cost": 0.05}))
    assert "No safety buffer" in out.summary


def test_summary_lists_active_signals():
    out = loop.run(CalibrationLoopInput("svc", {"cost": 0.25, "latency": 0.22}))
    assert "cost" in out.summary
    assert "latency" in out.summary


# ── run_from_entries ──────────────────────────────────────────────────────────

def test_run_from_entries_worst_case():
    entries = [
        make_entry("cost", predicted=1100, actual=1000),  # delta 0.10
        make_entry("cost", predicted=1300, actual=1000),  # delta 0.30 — worst
        make_entry("latency", predicted=115, actual=100), # delta 0.15
    ]
    out = loop.run_from_entries("lambda", entries)
    assert out.result.safety_buffer.applied
    assert out.result.safety_buffer.cost_multiplier == pytest.approx(1.15)
    # latency 0.15 < 0.20 → no latency buffer
    assert out.result.safety_buffer.latency_multiplier == pytest.approx(1.0)


def test_run_from_entries_empty_no_buffer():
    out = loop.run_from_entries("lambda", [])
    assert not out.result.safety_buffer.applied


def test_run_from_entries_uses_worst_not_average():
    entries = [
        make_entry("cost", predicted=1050, actual=1000),  # delta 0.05
        make_entry("cost", predicted=1250, actual=1000),  # delta 0.25 — worst
    ]
    out = loop.run_from_entries("ecs", entries)
    # Worst is 0.25 > 0.20 → buffer applied
    assert out.result.safety_buffer.applied
