from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.enums import VetoGateResult, VetoGateType
from isa_cad.core.models.reviewer import PerformanceReviewerOutput
from isa_cad.core.models.veto import VetoGate


# ── Thresholds ────────────────────────────────────────────────────────────────

# P95 latency regression above this % → BLOCKED
_LATENCY_BLOCK_PCT   = 100.0
# P95 latency regression above this % → DEGRADED
_LATENCY_DEGRADE_PCT = 50.0

# Throughput ceiling below which we flag (RPS)
_THROUGHPUT_BLOCK_RPS   = 50.0
_THROUGHPUT_DEGRADE_RPS = 150.0

# Performance score below which we block / degrade
_SCORE_BLOCK_THRESHOLD   = 0.25
_SCORE_DEGRADE_THRESHOLD = 0.50


def _latency_delta_pct(review: PerformanceReviewerOutput) -> float | None:
    """Extract latency delta % from P95 values if available."""
    if (
        review.p95_baseline_ms is not None
        and review.p95_projected_ms is not None
        and review.p95_baseline_ms > 0
    ):
        return (
            (review.p95_projected_ms - review.p95_baseline_ms)
            / review.p95_baseline_ms
            * 100.0
        )
    return None


def evaluate_reliability_gate(review: PerformanceReviewerOutput) -> VetoGate:
    """
    Pure function — evaluates the reliability veto gate from a
    PerformanceReviewerOutput and returns a VetoGate.

    BLOCKED (G_j = 0.0) when ANY of:
        • bottleneck_risk == "high"  AND  db_pressure_risk == "high"
          (cascading DB failure risk)
        • P95 latency regression > 100 %
        • throughput_rps < 50 RPS  (system barely functional)
        • performance score < 0.25

    DEGRADED (G_j = 0.5) when ANY of (and not already BLOCKED):
        • db_pressure_risk == "high"
        • queue_pressure_risk == "high"
        • bottleneck_risk == "high"
        • P95 latency regression > 50 %
        • cold_start_risk == "high"
        • throughput_rps < 150 RPS
        • performance score < 0.50

    PASSED (G_j = 1.0) otherwise.
    """
    score        = review.score
    bottleneck   = review.bottleneck_risk   or "low"
    db_pressure  = review.db_pressure_risk  or "low"
    queue_risk   = review.queue_pressure_risk or "low"
    cold_start   = review.cold_start_risk   or "low"
    throughput   = review.throughput_rps
    lat_delta    = _latency_delta_pct(review)

    # ── BLOCKED ───────────────────────────────────────────────────────────────
    block_reasons: list[str] = []

    # Cascading DB failure: high bottleneck + high DB pressure together
    if bottleneck == "high" and db_pressure == "high":
        block_reasons.append(
            "High bottleneck risk combined with high DB fan-in — "
            "connection pool exhaustion may cause cascading failure."
        )

    if lat_delta is not None and lat_delta > _LATENCY_BLOCK_PCT:
        block_reasons.append(
            f"P95 latency regression {lat_delta:.1f}% exceeds block threshold "
            f"({_LATENCY_BLOCK_PCT:.0f}%). "
            f"{review.p95_baseline_ms:.1f}ms → {review.p95_projected_ms:.1f}ms."
        )

    if throughput is not None and throughput < _THROUGHPUT_BLOCK_RPS:
        block_reasons.append(
            f"Throughput ceiling {throughput:.0f} RPS is below the minimum "
            f"viable threshold ({_THROUGHPUT_BLOCK_RPS:.0f} RPS)."
        )

    if score < _SCORE_BLOCK_THRESHOLD:
        block_reasons.append(
            f"Performance score {score:.2f} is below the block threshold "
            f"({_SCORE_BLOCK_THRESHOLD})."
        )

    if block_reasons:
        return VetoGate(
            gate_type=VetoGateType.RELIABILITY,
            result=VetoGateResult.BLOCKED,
            reason="Reliability gate BLOCKED: " + " | ".join(block_reasons),
            required_action=(
                "Resolve reliability risks before proceeding. "
                "Address DB fan-in (add connection pooler / read replica), "
                "profile the latency regression, "
                "and ensure throughput meets minimum SLA."
            ),
        )

    # ── DEGRADED ──────────────────────────────────────────────────────────────
    degrade_reasons: list[str] = []

    if db_pressure == "high":
        degrade_reasons.append(
            "High DB fan-in — multiple services share a single database "
            "connection pool. Risk of contention under load."
        )

    if queue_risk == "high":
        degrade_reasons.append(
            "High queue producer fan-in — consumer lag and backpressure "
            "may degrade dependent services."
        )

    if bottleneck == "high":
        degrade_reasons.append(
            "High bottleneck risk detected — Tier-1 or shared resource "
            "contention may amplify failures."
        )

    if lat_delta is not None and lat_delta > _LATENCY_DEGRADE_PCT:
        degrade_reasons.append(
            f"P95 latency regression {lat_delta:.1f}% exceeds degrade threshold "
            f"({_LATENCY_DEGRADE_PCT:.0f}%)."
        )

    if cold_start == "high":
        degrade_reasons.append(
            "Cold-start risk present — serverless/lambda nodes may add "
            "200ms+ P99 tail latency on first invocation."
        )

    if throughput is not None and throughput < _THROUGHPUT_DEGRADE_RPS:
        degrade_reasons.append(
            f"Throughput ceiling {throughput:.0f} RPS is below the "
            f"recommended minimum ({_THROUGHPUT_DEGRADE_RPS:.0f} RPS)."
        )

    if score < _SCORE_DEGRADE_THRESHOLD:
        degrade_reasons.append(
            f"Performance score {score:.2f} is below the degrade threshold "
            f"({_SCORE_DEGRADE_THRESHOLD})."
        )

    if degrade_reasons:
        return VetoGate(
            gate_type=VetoGateType.RELIABILITY,
            result=VetoGateResult.DEGRADED,
            reason="Reliability gate DEGRADED (G_j=0.5): " + " | ".join(degrade_reasons),
            required_action=(
                "Address reliability concerns before production deploy. "
                "Human review required. "
                "Proposal may proceed to sandbox for load testing."
            ),
        )

    # ── PASSED ────────────────────────────────────────────────────────────────
    lat_note = (
        f", P95 Δ={lat_delta:+.1f}%" if lat_delta is not None else ""
    )
    tput_note = (
        f", throughput={throughput:.0f} RPS" if throughput is not None else ""
    )
    return VetoGate(
        gate_type=VetoGateType.RELIABILITY,
        result=VetoGateResult.PASSED,
        reason=(
            f"Reliability gate PASSED (score={score:.2f}{lat_note}{tput_note}). "
            "No critical bottlenecks or latency regressions detected."
        ),
        required_action=None,
    )


class ReliabilityVetoGate:
    """
    LangGraph node — evaluates the reliability veto gate.

    Reads:   state["performance_review"]
    Writes:  state["reliability_gate"]  (VetoGate)

    Signals evaluated:
        • DB fan-in + bottleneck (cascading failure risk → BLOCKED)
        • P95 latency regression % vs baseline
        • Throughput ceiling (weakest-link RPS)
        • Cold-start risk (P99 tail)
        • Performance score
    """

    def __call__(self, state: AgentState) -> AgentState:
        review: PerformanceReviewerOutput | None = state.get("performance_review")

        if review is None:
            gate = VetoGate(
                gate_type=VetoGateType.RELIABILITY,
                result=VetoGateResult.DEGRADED,
                reason="Reliability gate DEGRADED: no performance_review in state.",
                required_action="Run PerformanceReviewerNode before ReliabilityVetoGate.",
            )
        else:
            gate = evaluate_reliability_gate(review)

        return {"reliability_gate": gate}
