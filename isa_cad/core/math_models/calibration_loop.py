from __future__ import annotations

from dataclasses import dataclass, field

from isa_cad.config.settings import settings
from isa_cad.core.models.calibration import CalibrationError, CalibrationResult, SafetyBuffer
from isa_cad.core.models.calibration_record import CalibrationEntry


# ── Calibration signals (Section 6.1 table) ───────────────────────────────────

CALIBRATION_SIGNALS = {
    "cost":                   "cost forecast error",
    "latency":                "latency forecast error",
    "security_false_negative": "security false negative",
    "blast_radius":           "blast radius underestimation",
}


# ── Input / Output ────────────────────────────────────────────────────────────

@dataclass
class CalibrationLoopInput:
    """
    Input for the Self-Calibration Loop.
    Holds per-metric historical error data derived from CalibrationStore entries.
    Section 6.1 — CalibrationAndBiasAdjustmentNode.
    """
    component_class: str
    metric_deltas: dict[str, float] = field(default_factory=dict)
    # e.g. {"cost": 0.24, "latency": 0.18, "blast_radius": 0.05}

    entries_used: list[CalibrationEntry] = field(default_factory=list)
    enabled_for_existing_system: bool = True


@dataclass
class CalibrationLoopOutput:
    """
    Full output of the Self-Calibration Loop.
    Contains CalibrationResult (with SafetyBuffer) + per-signal action notes.
    """
    result: CalibrationResult
    signal_actions: dict[str, str] = field(default_factory=dict)
    # e.g. {"cost": "+15% safety buffer applied", "blast_radius": "traversal depth increased"}
    summary: str = ""
    # Actionable flags consumed by downstream nodes
    increase_blast_radius_depth: bool = False   # True when blast_radius delta > 20%
    human_review_required: bool = False          # True when security false negative detected


# ── Self-Calibration Loop ─────────────────────────────────────────────────────

class SelfCalibrationLoop:
    """
    Implements the Self-Calibration Loop from Section 6.1 of the convention.

    Algorithm:
        historical_error_delta = ABS(predicted - actual) / actual

        if historical_error_delta > 0.20:
            cost_estimate    = cost_estimate * 1.15
            latency_estimate = latency_estimate * 1.15
            add bias_note    = "Historical forecast delta exceeded 20%; +15% safety buffer applied."

    Calibration signals and their actions (Section 6.1 table):
        cost forecast error     > 20%  → +15% safety buffer on cost
        latency forecast error  > 20%  → +15% safety buffer on latency
        security false negative (any)  → raise SecurityReviewer strictness + human review
        blast radius underestimation   > 20% → increase graph traversal depth / multiplier
    """

    def run(self, inp: CalibrationLoopInput) -> CalibrationLoopOutput:
        threshold  = settings.CALIBRATION_BUFFER_THRESHOLD   # 0.20
        multiplier = settings.SAFETY_BUFFER_MULTIPLIER        # 1.15

        errors: list[CalibrationError] = []
        signal_actions: dict[str, str] = {}
        notes: list[str] = []

        for metric, delta in inp.metric_deltas.items():
            if metric not in ("cost", "latency", "security_false_negative", "blast_radius"):
                continue

            # Build synthetic CalibrationError (preserves delta ratio)
            if delta > 0:
                errors.append(CalibrationError(
                    metric=metric,
                    predicted_value=round(1.0 + delta, 6),
                    actual_value=1.0,
                ))

        # Use CalibrationResult's existing logic for cost/latency buffer
        cal_result = CalibrationResult(
            enabled_for_existing_system=inp.enabled_for_existing_system,
            historical_errors=errors,
        )
        cal_result.apply_buffer_if_needed()

        # ── Per-signal action notes (Section 6.1 table) ──────────────────────

        cost_delta    = inp.metric_deltas.get("cost", 0.0)
        latency_delta = inp.metric_deltas.get("latency", 0.0)
        sec_fn        = inp.metric_deltas.get("security_false_negative", 0.0)
        br_delta      = inp.metric_deltas.get("blast_radius", 0.0)

        if cost_delta > threshold:
            signal_actions["cost"] = (
                f"+{round((multiplier - 1) * 100)}% safety buffer applied to cost estimates "
                f"for component class '{inp.component_class}' "
                f"(historical delta {round(cost_delta * 100, 1)}% > {int(threshold * 100)}%)."
            )
            notes.append(signal_actions["cost"])

        if latency_delta > threshold:
            signal_actions["latency"] = (
                f"+{round((multiplier - 1) * 100)}% safety buffer applied to p95/p99 estimates "
                f"for component class '{inp.component_class}' "
                f"(historical delta {round(latency_delta * 100, 1)}% > {int(threshold * 100)}%)."
            )
            notes.append(signal_actions["latency"])

        if sec_fn > 0:
            signal_actions["security_false_negative"] = (
                "Security false negative detected. "
                "SecurityReviewer strictness raised. "
                "Human review required on next proposal for this component class."
            )
            notes.append(signal_actions["security_false_negative"])

        if br_delta > threshold:
            signal_actions["blast_radius"] = (
                f"Blast radius underestimation detected "
                f"({round(br_delta * 100, 1)}% > {int(threshold * 100)}%). "
                "Increase graph traversal depth or criticality multiplier for matching patterns."
            )
            notes.append(signal_actions["blast_radius"])

        cal_result.calibration_notes = notes

        summary = _build_summary(inp.component_class, cal_result, signal_actions)

        return CalibrationLoopOutput(
            result=cal_result,
            signal_actions=signal_actions,
            summary=summary,
            increase_blast_radius_depth="blast_radius" in signal_actions,
            human_review_required="security_false_negative" in signal_actions,
        )

    def run_from_entries(
        self,
        component_class: str,
        entries: list[CalibrationEntry],
        enabled_for_existing_system: bool = True,
    ) -> CalibrationLoopOutput:
        """
        Convenience: derive metric_deltas from a list of CalibrationEntry objects
        (worst-case delta per metric) and run the loop.
        """
        worst: dict[str, float] = {}
        for entry in entries:
            m = entry.forecast.metric
            if entry.error_delta > worst.get(m, 0.0):
                worst[m] = entry.error_delta

        return self.run(CalibrationLoopInput(
            component_class=component_class,
            metric_deltas=worst,
            entries_used=entries,
            enabled_for_existing_system=enabled_for_existing_system,
        ))


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_summary(
    component_class: str,
    result: CalibrationResult,
    signal_actions: dict[str, str],
) -> str:
    parts: list[str] = [f"Calibration for '{component_class}':"]

    if not result.enabled_for_existing_system:
        return f"Calibration for '{component_class}': no historical data — skipped."

    if result.safety_buffer.applied:
        parts.append(
            f"Safety buffer ×{result.safety_buffer.cost_multiplier} on cost, "
            f"×{result.safety_buffer.latency_multiplier} on latency."
        )
    else:
        parts.append("No safety buffer needed (all deltas within threshold).")

    if signal_actions:
        parts.append(f"Active signals: {', '.join(signal_actions.keys())}.")

    return " ".join(parts)
