from __future__ import annotations

import pytest
from dataclasses import replace

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.veto.fidelity_gate import (
    FidelityVetoGate,
    _CONFIDENCE_BLOCK_THRESHOLD,
    _CONFIDENCE_DEGRADE_THRESHOLD,
    evaluate_fidelity_gate,
)
from isa_cad.config.settings import settings
from isa_cad.core.freshness_engine import FreshnessReport
from isa_cad.core.models.enums import OutputMode, VetoGateResult, VetoGateType

gate_node = FidelityVetoGate()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_report(
    adjusted_confidence: float = 0.90,
    output_mode: OutputMode = OutputMode.FINAL_FORECAST,
    require_refresh: bool = False,
    stale_sources: list[str] | None = None,
    freshness_score: float = 1.0,
) -> FreshnessReport:
    return FreshnessReport(
        freshness_score=freshness_score,
        adjusted_confidence=adjusted_confidence,
        output_mode=output_mode,
        require_observed_graph_refresh=require_refresh,
        stale_sources=stale_sources or [],
    )


def run_gate(
    report: FreshnessReport,
    combined_confidence: float | None = None,
) -> dict:
    state: AgentState = {"freshness_report": report}
    if combined_confidence is not None:
        state["reviewer_summary"] = {"combined_confidence": combined_confidence}
    return gate_node(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_key_present():
    assert "fidelity_gate" in run_gate(make_report())


def test_gate_type_is_fidelity():
    assert run_gate(make_report())["fidelity_gate"].gate_type == VetoGateType.FIDELITY


def test_multiplier_synced_with_result():
    gate = run_gate(make_report())["fidelity_gate"]
    expected = {VetoGateResult.PASSED: 1.0, VetoGateResult.DEGRADED: 0.5, VetoGateResult.BLOCKED: 0.0}
    assert gate.multiplier == expected[gate.result]


def test_no_report_in_state_gives_degraded():
    gate = gate_node({})["fidelity_gate"]
    assert gate.result == VetoGateResult.DEGRADED
    assert gate.required_action is not None


# ── PASSED ────────────────────────────────────────────────────────────────────

def test_fresh_final_forecast_passes():
    gate = evaluate_fidelity_gate(make_report(
        adjusted_confidence=0.92,
        output_mode=OutputMode.FINAL_FORECAST,
    ))
    assert gate.result == VetoGateResult.PASSED
    assert gate.multiplier == 1.0
    assert gate.required_action is None


def test_pass_reason_contains_confidence_and_mode():
    gate = evaluate_fidelity_gate(make_report(adjusted_confidence=0.88))
    assert "0.88" in gate.reason
    assert "final_forecast" in gate.reason.lower() or "FINAL" in gate.reason


def test_pass_with_good_combined_reviewer_confidence():
    gate = evaluate_fidelity_gate(
        make_report(adjusted_confidence=0.90),
        combined_reviewer_confidence=0.75,
    )
    assert gate.result == VetoGateResult.PASSED
    assert "0.75" in gate.reason


# ── BLOCKED — exploratory + low confidence ────────────────────────────────────

def test_exploratory_with_low_confidence_blocks():
    gate = evaluate_fidelity_gate(make_report(
        output_mode=OutputMode.EXPLORATORY_ESTIMATE,
        adjusted_confidence=_CONFIDENCE_BLOCK_THRESHOLD - 0.01,
    ))
    assert gate.result == VetoGateResult.BLOCKED
    assert gate.multiplier == 0.0
    assert "EXPLORATORY" in gate.reason or "exploratory" in gate.reason.lower()


def test_exploratory_with_ok_confidence_degrades_not_blocks():
    """Exploratory mode alone (confidence is OK) → DEGRADED only."""
    gate = evaluate_fidelity_gate(make_report(
        output_mode=OutputMode.EXPLORATORY_ESTIMATE,
        adjusted_confidence=_CONFIDENCE_BLOCK_THRESHOLD + 0.05,
    ))
    assert gate.result == VetoGateResult.DEGRADED


# ── BLOCKED — require_refresh + low confidence ───────────────────────────────

def test_require_refresh_with_low_confidence_blocks():
    gate = evaluate_fidelity_gate(make_report(
        require_refresh=True,
        adjusted_confidence=_CONFIDENCE_BLOCK_THRESHOLD - 0.01,
    ))
    assert gate.result == VetoGateResult.BLOCKED
    assert "refresh" in gate.reason.lower()


def test_require_refresh_with_ok_confidence_degrades():
    gate = evaluate_fidelity_gate(make_report(
        require_refresh=True,
        adjusted_confidence=_CONFIDENCE_BLOCK_THRESHOLD + 0.05,
    ))
    assert gate.result == VetoGateResult.DEGRADED


# ── BLOCKED — critically low confidence ──────────────────────────────────────

def test_critically_low_confidence_blocks():
    hard_threshold = _CONFIDENCE_BLOCK_THRESHOLD - 0.10
    gate = evaluate_fidelity_gate(make_report(
        adjusted_confidence=hard_threshold - 0.01,
    ))
    assert gate.result == VetoGateResult.BLOCKED


def test_exactly_at_hard_block_threshold_does_not_block():
    hard_threshold = _CONFIDENCE_BLOCK_THRESHOLD - 0.10
    gate = evaluate_fidelity_gate(make_report(
        adjusted_confidence=hard_threshold,
    ))
    assert gate.result != VetoGateResult.BLOCKED


# ── DEGRADED — individual signals ────────────────────────────────────────────

def test_exploratory_mode_alone_degrades():
    gate = evaluate_fidelity_gate(make_report(
        output_mode=OutputMode.EXPLORATORY_ESTIMATE,
        adjusted_confidence=0.80,
    ))
    assert gate.result == VetoGateResult.DEGRADED
    assert "EXPLORATORY" in gate.reason or "exploratory" in gate.reason.lower()


def test_require_refresh_alone_degrades():
    gate = evaluate_fidelity_gate(make_report(
        require_refresh=True,
        adjusted_confidence=0.80,
    ))
    assert gate.result == VetoGateResult.DEGRADED
    assert "refresh" in gate.reason.lower()


def test_stale_sources_degrade():
    gate = evaluate_fidelity_gate(make_report(
        stale_sources=["cloud_inventory", "runtime_metrics"],
        adjusted_confidence=0.80,
    ))
    assert gate.result == VetoGateResult.DEGRADED
    assert "cloud_inventory" in gate.reason or "stale" in gate.reason.lower()


def test_confidence_between_thresholds_degrades():
    confidence = (_CONFIDENCE_BLOCK_THRESHOLD + _CONFIDENCE_DEGRADE_THRESHOLD) / 2
    gate = evaluate_fidelity_gate(make_report(adjusted_confidence=confidence))
    assert gate.result == VetoGateResult.DEGRADED


def test_confidence_exactly_at_degrade_threshold_passes():
    gate = evaluate_fidelity_gate(make_report(
        adjusted_confidence=_CONFIDENCE_DEGRADE_THRESHOLD,
    ))
    assert gate.result == VetoGateResult.PASSED


def test_low_combined_reviewer_confidence_degrades():
    gate = evaluate_fidelity_gate(
        make_report(adjusted_confidence=0.90),
        combined_reviewer_confidence=0.35,
    )
    assert gate.result == VetoGateResult.DEGRADED
    assert "reviewer" in gate.reason.lower() or "0.35" in gate.reason


def test_ok_combined_reviewer_confidence_does_not_degrade():
    gate = evaluate_fidelity_gate(
        make_report(adjusted_confidence=0.90),
        combined_reviewer_confidence=0.70,
    )
    assert gate.result == VetoGateResult.PASSED


# ── Threshold boundary precision ─────────────────────────────────────────────

def test_confidence_exactly_at_block_threshold_does_not_block_on_score_alone():
    """At exactly MIN_CONFIDENCE, not exploratory, no refresh → PASSED."""
    gate = evaluate_fidelity_gate(make_report(
        adjusted_confidence=_CONFIDENCE_BLOCK_THRESHOLD,
        output_mode=OutputMode.FINAL_FORECAST,
        require_refresh=False,
    ))
    # Confidence = exactly MIN_CONFIDENCE, degrade threshold = MIN+0.10
    # Still below degrade threshold → DEGRADED
    assert gate.result == VetoGateResult.DEGRADED


# ── required_action ───────────────────────────────────────────────────────────

def test_blocked_has_required_action():
    gate = evaluate_fidelity_gate(make_report(
        output_mode=OutputMode.EXPLORATORY_ESTIMATE,
        adjusted_confidence=_CONFIDENCE_BLOCK_THRESHOLD - 0.05,
    ))
    assert gate.required_action is not None
    assert "Refresh" in gate.required_action or "refresh" in gate.required_action.lower()


def test_degraded_has_required_action():
    gate = evaluate_fidelity_gate(make_report(require_refresh=True, adjusted_confidence=0.80))
    assert gate.required_action is not None


def test_passed_has_no_required_action():
    gate = evaluate_fidelity_gate(make_report(adjusted_confidence=0.95))
    assert gate.required_action is None


# ── reviewer_summary integration ─────────────────────────────────────────────

def test_reviewer_summary_confidence_read_from_state():
    report = make_report(adjusted_confidence=0.90)
    state: AgentState = {
        "freshness_report": report,
        "reviewer_summary": {"combined_confidence": 0.30},
    }
    result = gate_node(state)
    assert result["fidelity_gate"].result == VetoGateResult.DEGRADED


def test_missing_reviewer_summary_does_not_crash():
    report = make_report(adjusted_confidence=0.90)
    state: AgentState = {"freshness_report": report}
    result = gate_node(state)
    assert "fidelity_gate" in result


# ── output contract ───────────────────────────────────────────────────────────

def test_existing_state_keys_preserved():
    state: AgentState = {
        "freshness_report": make_report(),
        "session_id": "sess-fidelity",
    }
    result = gate_node(state)
    assert "fidelity_gate" in result
    assert list(result.keys()) == ["fidelity_gate"]
