from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.config.settings import settings
from isa_cad.core.freshness_engine import FreshnessReport
from isa_cad.core.models.enums import OutputMode, VetoGateResult, VetoGateType
from isa_cad.core.models.veto import VetoGate


# ── Thresholds ────────────────────────────────────────────────────────────────

# adjusted_confidence below this → BLOCKED  (from settings: 0.65 default)
_CONFIDENCE_BLOCK_THRESHOLD  = settings.MIN_CONFIDENCE

# adjusted_confidence below this (but above block) → DEGRADED
_CONFIDENCE_DEGRADE_THRESHOLD = _CONFIDENCE_BLOCK_THRESHOLD + 0.10   # 0.75


def evaluate_fidelity_gate(
    freshness_report: FreshnessReport,
    combined_reviewer_confidence: float | None = None,
) -> VetoGate:
    """
    Pure function — evaluates the fidelity veto gate.

    Fidelity = confidence that the simulation reflects reality.
    Sources of fidelity loss:
        • Stale data (freshness_score < 1.0, stale_sources non-empty)
        • Exploratory output mode (any source > 7 days old)
        • adjusted_confidence < MIN_CONFIDENCE
        • require_observed_graph_refresh = True
        • Low combined reviewer confidence (heuristic-heavy analysis)

    BLOCKED (G_j = 0.0) when ANY of:
        • output_mode == EXPLORATORY_ESTIMATE
          AND adjusted_confidence < MIN_CONFIDENCE
          (stale + low confidence → output is unreliable for decisions)
        • require_observed_graph_refresh == True
          AND adjusted_confidence < MIN_CONFIDENCE
        • adjusted_confidence < MIN_CONFIDENCE − 0.10  (very low, hard block)

    DEGRADED (G_j = 0.5) when ANY of (and not already BLOCKED):
        • output_mode == EXPLORATORY_ESTIMATE
        • require_observed_graph_refresh == True
        • adjusted_confidence < _CONFIDENCE_DEGRADE_THRESHOLD
        • combined_reviewer_confidence is not None
          AND combined_reviewer_confidence < 0.40
        • stale_sources non-empty

    PASSED (G_j = 1.0) otherwise.
    """
    confidence   = freshness_report.adjusted_confidence
    output_mode  = freshness_report.output_mode
    need_refresh = freshness_report.require_observed_graph_refresh
    stale        = freshness_report.stale_sources
    is_exploratory = output_mode == OutputMode.EXPLORATORY_ESTIMATE

    hard_block_threshold = _CONFIDENCE_BLOCK_THRESHOLD - 0.10

    # ── BLOCKED ───────────────────────────────────────────────────────────────
    block_reasons: list[str] = []

    if is_exploratory and confidence < _CONFIDENCE_BLOCK_THRESHOLD:
        block_reasons.append(
            f"Output mode is EXPLORATORY_ESTIMATE with adjusted confidence "
            f"{confidence:.2f} < {_CONFIDENCE_BLOCK_THRESHOLD} — "
            "simulation fidelity is too low for a binding decision."
        )

    if need_refresh and confidence < _CONFIDENCE_BLOCK_THRESHOLD:
        block_reasons.append(
            f"Observed Graph refresh is required (confidence {confidence:.2f} "
            f"< {_CONFIDENCE_BLOCK_THRESHOLD}) — stale data would invalidate "
            "any forecast produced."
        )

    if confidence < hard_block_threshold:
        block_reasons.append(
            f"Adjusted confidence {confidence:.2f} is critically low "
            f"(threshold {hard_block_threshold:.2f}) — "
            "data sources are too stale to support any architectural decision."
        )

    if block_reasons:
        return VetoGate(
            gate_type=VetoGateType.FIDELITY,
            result=VetoGateResult.BLOCKED,
            reason="Fidelity gate BLOCKED: " + " | ".join(block_reasons),
            required_action=(
                "Refresh the Observed Graph before re-running this analysis. "
                "Ensure cloud inventory and runtime metrics are collected within "
                f"the last {settings.STALE_DATA_DAYS} days. "
                "Do not proceed with a decision until fidelity is restored."
            ),
        )

    # ── DEGRADED ──────────────────────────────────────────────────────────────
    degrade_reasons: list[str] = []

    if is_exploratory:
        degrade_reasons.append(
            "Output mode is EXPLORATORY_ESTIMATE — at least one data source "
            "is older than the freshness threshold. "
            "Outputs are estimates only, not final forecasts."
        )

    if need_refresh:
        degrade_reasons.append(
            "Observed Graph refresh is recommended to increase forecast confidence."
        )

    if confidence < _CONFIDENCE_DEGRADE_THRESHOLD:
        degrade_reasons.append(
            f"Adjusted confidence {confidence:.2f} < degrade threshold "
            f"{_CONFIDENCE_DEGRADE_THRESHOLD:.2f}."
        )

    if stale:
        degrade_reasons.append(
            f"Stale data sources: {', '.join(stale)}. "
            "Freshness-adjusted confidence is reduced."
        )

    if (
        combined_reviewer_confidence is not None
        and combined_reviewer_confidence < 0.40
    ):
        degrade_reasons.append(
            f"Combined reviewer confidence {combined_reviewer_confidence:.2f} < 0.40 — "
            "reviewers relied heavily on heuristics rather than observed metrics."
        )

    if degrade_reasons:
        return VetoGate(
            gate_type=VetoGateType.FIDELITY,
            result=VetoGateResult.DEGRADED,
            reason="Fidelity gate DEGRADED (G_j=0.5): " + " | ".join(degrade_reasons),
            required_action=(
                "Treat all outputs as preliminary estimates. "
                "Refresh stale data sources and re-run analysis before "
                "making a production architecture decision. "
                "Human review required."
            ),
        )

    # ── PASSED ────────────────────────────────────────────────────────────────
    reviewer_note = (
        f", reviewer confidence={combined_reviewer_confidence:.2f}"
        if combined_reviewer_confidence is not None
        else ""
    )
    return VetoGate(
        gate_type=VetoGateType.FIDELITY,
        result=VetoGateResult.PASSED,
        reason=(
            f"Fidelity gate PASSED "
            f"(adjusted_confidence={confidence:.2f}{reviewer_note}, "
            f"output_mode={output_mode.value}). "
            "Data freshness and simulation fidelity are acceptable."
        ),
        required_action=None,
    )


class FidelityVetoGate:
    """
    LangGraph node — evaluates the fidelity veto gate.

    Reads:
        state["freshness_report"]        (FreshnessReport from ContextAndFreshnessNode)
        state["reviewer_summary"]        (optional — uses combined_confidence)

    Writes:
        state["fidelity_gate"]           (VetoGate)

    The fidelity gate is the only gate that does not care about the
    architectural content of the proposal — it only asks:
        "Is our simulation trustworthy enough to act on?"
    """

    def __call__(self, state: AgentState) -> AgentState:
        report: FreshnessReport | None = state.get("freshness_report")

        if report is None:
            gate = VetoGate(
                gate_type=VetoGateType.FIDELITY,
                result=VetoGateResult.DEGRADED,
                reason="Fidelity gate DEGRADED: no freshness_report in state.",
                required_action=(
                    "Run ContextAndFreshnessNode before FidelityVetoGate."
                ),
            )
            return {"fidelity_gate": gate}

        # Extract combined reviewer confidence if available
        summary = state.get("reviewer_summary") or {}
        combined_confidence: float | None = summary.get("combined_confidence")

        gate = evaluate_fidelity_gate(report, combined_confidence)
        return {"fidelity_gate": gate}
