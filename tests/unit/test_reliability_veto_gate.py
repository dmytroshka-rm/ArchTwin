from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.veto.reliability_gate import (
    ReliabilityVetoGate,
    _LATENCY_BLOCK_PCT,
    _LATENCY_DEGRADE_PCT,
    _SCORE_BLOCK_THRESHOLD,
    _SCORE_DEGRADE_THRESHOLD,
    _THROUGHPUT_BLOCK_RPS,
    _THROUGHPUT_DEGRADE_RPS,
    evaluate_reliability_gate,
)
from isa_cad.core.models.enums import ReviewerStatus, VetoGateResult, VetoGateType
from isa_cad.core.models.reviewer import PerformanceReviewerOutput

gate_node = ReliabilityVetoGate()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_review(
    score: float = 0.8,
    bottleneck_risk: str = "low",
    db_pressure_risk: str = "low",
    queue_pressure_risk: str = "low",
    cold_start_risk: str = "low",
    throughput_rps: float | None = 500.0,
    p95_baseline_ms: float | None = 50.0,
    p95_projected_ms: float | None = 55.0,
    p99_baseline_ms: float | None = 75.0,
    p99_projected_ms: float | None = 82.0,
    status: ReviewerStatus = ReviewerStatus.PASS,
) -> PerformanceReviewerOutput:
    return PerformanceReviewerOutput(
        status=status,
        score=score,
        confidence=0.7,
        recommendation="ok",
        bottleneck_risk=bottleneck_risk,
        db_pressure_risk=db_pressure_risk,
        queue_pressure_risk=queue_pressure_risk,
        cold_start_risk=cold_start_risk,
        throughput_rps=throughput_rps,
        p95_baseline_ms=p95_baseline_ms,
        p95_projected_ms=p95_projected_ms,
        p99_baseline_ms=p99_baseline_ms,
        p99_projected_ms=p99_projected_ms,
        latency_delta="+5.0ms (+10.0%)",
    )


def run_gate(review: PerformanceReviewerOutput) -> dict:
    state: AgentState = {"performance_review": review}
    return gate_node(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_key_present():
    result = run_gate(make_review())
    assert "reliability_gate" in result


def test_gate_type_is_reliability():
    result = run_gate(make_review())
    assert result["reliability_gate"].gate_type == VetoGateType.RELIABILITY


def test_multiplier_synced_with_result():
    gate = run_gate(make_review())["reliability_gate"]
    expected = {VetoGateResult.PASSED: 1.0, VetoGateResult.DEGRADED: 0.5, VetoGateResult.BLOCKED: 0.0}
    assert gate.multiplier == expected[gate.result]


def test_no_review_in_state_gives_degraded():
    result = gate_node({})
    gate = result["reliability_gate"]
    assert gate.result == VetoGateResult.DEGRADED
    assert gate.required_action is not None


# ── PASSED ────────────────────────────────────────────────────────────────────

def test_clean_review_passes():
    gate = evaluate_reliability_gate(make_review(score=0.85))
    assert gate.result == VetoGateResult.PASSED
    assert gate.multiplier == 1.0
    assert gate.required_action is None


def test_pass_reason_contains_score():
    gate = evaluate_reliability_gate(make_review(score=0.82))
    assert "0.82" in gate.reason


def test_pass_reason_contains_latency_delta():
    gate = evaluate_reliability_gate(make_review(
        p95_baseline_ms=50.0, p95_projected_ms=55.0,
    ))
    assert "Δ" in gate.reason or "delta" in gate.reason.lower() or "+" in gate.reason


def test_pass_reason_contains_throughput():
    gate = evaluate_reliability_gate(make_review(throughput_rps=1000.0))
    assert "1000" in gate.reason


# ── BLOCKED — cascading DB failure ───────────────────────────────────────────

def test_high_bottleneck_plus_high_db_blocks():
    review = make_review(bottleneck_risk="high", db_pressure_risk="high")
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.BLOCKED
    assert gate.multiplier == 0.0
    assert "cascading" in gate.reason.lower() or "DB" in gate.reason


def test_high_bottleneck_alone_degrades_not_blocks():
    review = make_review(bottleneck_risk="high", db_pressure_risk="low")
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.DEGRADED


def test_high_db_alone_degrades_not_blocks():
    review = make_review(bottleneck_risk="low", db_pressure_risk="high")
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.DEGRADED


# ── BLOCKED — latency regression ─────────────────────────────────────────────

def test_latency_regression_above_block_pct_blocks():
    base = 50.0
    proposed = base * (1 + _LATENCY_BLOCK_PCT / 100.0 + 0.01)
    review = make_review(p95_baseline_ms=base, p95_projected_ms=proposed)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.BLOCKED
    assert "latency" in gate.reason.lower() or "P95" in gate.reason


def test_latency_regression_exactly_at_block_does_not_block():
    base = 50.0
    proposed = base * (1 + _LATENCY_BLOCK_PCT / 100.0)  # exactly 100%
    review = make_review(p95_baseline_ms=base, p95_projected_ms=proposed)
    gate = evaluate_reliability_gate(review)
    assert gate.result != VetoGateResult.BLOCKED


def test_no_latency_data_does_not_block_on_latency():
    review = make_review(p95_baseline_ms=None, p95_projected_ms=None)
    gate = evaluate_reliability_gate(review)
    # Should not block purely due to missing latency data
    assert gate.result != VetoGateResult.BLOCKED


# ── BLOCKED — throughput ──────────────────────────────────────────────────────

def test_throughput_below_block_rps_blocks():
    review = make_review(throughput_rps=_THROUGHPUT_BLOCK_RPS - 1)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.BLOCKED
    assert "throughput" in gate.reason.lower() or "RPS" in gate.reason


def test_throughput_exactly_at_block_does_not_block():
    review = make_review(throughput_rps=_THROUGHPUT_BLOCK_RPS)
    gate = evaluate_reliability_gate(review)
    assert gate.result != VetoGateResult.BLOCKED


def test_none_throughput_does_not_block():
    review = make_review(throughput_rps=None)
    gate = evaluate_reliability_gate(review)
    assert gate.result != VetoGateResult.BLOCKED


# ── BLOCKED — score ───────────────────────────────────────────────────────────

def test_score_below_block_threshold_blocks():
    review = make_review(score=_SCORE_BLOCK_THRESHOLD - 0.01)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.BLOCKED


def test_score_exactly_at_block_does_not_block():
    review = make_review(score=_SCORE_BLOCK_THRESHOLD)
    gate = evaluate_reliability_gate(review)
    assert gate.result != VetoGateResult.BLOCKED


# ── DEGRADED — individual signals ────────────────────────────────────────────

def test_high_db_pressure_alone_degrades():
    gate = evaluate_reliability_gate(make_review(db_pressure_risk="high"))
    assert gate.result == VetoGateResult.DEGRADED
    assert "DB" in gate.reason


def test_high_queue_risk_degrades():
    gate = evaluate_reliability_gate(make_review(queue_pressure_risk="high"))
    assert gate.result == VetoGateResult.DEGRADED
    assert "queue" in gate.reason.lower()


def test_high_cold_start_degrades():
    gate = evaluate_reliability_gate(make_review(cold_start_risk="high"))
    assert gate.result == VetoGateResult.DEGRADED
    assert "cold" in gate.reason.lower()


def test_latency_between_degrade_and_block_pct_degrades():
    base = 50.0
    proposed = base * (1 + (_LATENCY_DEGRADE_PCT + _LATENCY_BLOCK_PCT) / 2 / 100.0)
    review = make_review(p95_baseline_ms=base, p95_projected_ms=proposed)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.DEGRADED


def test_latency_below_degrade_pct_passes():
    base = 50.0
    proposed = base * (1 + (_LATENCY_DEGRADE_PCT - 5) / 100.0)
    review = make_review(p95_baseline_ms=base, p95_projected_ms=proposed)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.PASSED


def test_throughput_between_block_and_degrade_degrades():
    rps = (_THROUGHPUT_BLOCK_RPS + _THROUGHPUT_DEGRADE_RPS) / 2
    review = make_review(throughput_rps=rps)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.DEGRADED


def test_score_between_block_and_degrade_degrades():
    score = (_SCORE_BLOCK_THRESHOLD + _SCORE_DEGRADE_THRESHOLD) / 2
    review = make_review(score=score)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.DEGRADED


def test_score_exactly_at_degrade_threshold_passes():
    review = make_review(score=_SCORE_DEGRADE_THRESHOLD)
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.PASSED


# ── BLOCKED beats DEGRADED ────────────────────────────────────────────────────

def test_cascading_db_failure_blocks_even_with_ok_score():
    """bottleneck+db → BLOCKED even when score is fine."""
    review = make_review(
        score=0.80,
        bottleneck_risk="high",
        db_pressure_risk="high",
    )
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.BLOCKED


def test_very_low_throughput_blocks_even_with_degrading_signals():
    review = make_review(
        throughput_rps=1.0,
        cold_start_risk="high",   # would only degrade
        queue_pressure_risk="high",
    )
    gate = evaluate_reliability_gate(review)
    assert gate.result == VetoGateResult.BLOCKED


# ── required_action ───────────────────────────────────────────────────────────

def test_blocked_has_required_action():
    review = make_review(bottleneck_risk="high", db_pressure_risk="high")
    gate = evaluate_reliability_gate(review)
    assert gate.required_action is not None and len(gate.required_action) > 0


def test_degraded_has_required_action():
    gate = evaluate_reliability_gate(make_review(cold_start_risk="high"))
    assert gate.required_action is not None


def test_passed_has_no_required_action():
    gate = evaluate_reliability_gate(make_review(score=0.90))
    assert gate.required_action is None


# ── output contract ───────────────────────────────────────────────────────────

def test_existing_state_keys_preserved():
    review = make_review()
    state: AgentState = {"performance_review": review, "proposal_id": "p-001"}
    result = gate_node(state)
    assert "reliability_gate" in result
    assert list(result.keys()) == ["reliability_gate"]
