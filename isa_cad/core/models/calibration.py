from __future__ import annotations

from pydantic import Field

from .base import ISABaseModel
from isa_cad.config.settings import settings


class CalibrationError(ISABaseModel):
    """Historical forecast vs actual delta for a specific metric."""
    metric: str = Field(..., description="e.g. 'cost', 'latency'")
    predicted_value: float
    actual_value: float
    delta: float = Field(0.0, description="ABS(predicted - actual) / actual")

    def model_post_init(self, __context: object) -> None:
        if self.actual_value != 0:
            delta = abs(self.predicted_value - self.actual_value) / abs(self.actual_value)
            object.__setattr__(self, "delta", round(delta, 4))


class SafetyBuffer(ISABaseModel):
    """Safety buffer applied when historical forecast error exceeds threshold."""
    applied: bool = False
    reason: str | None = None
    cost_multiplier: float = 1.0
    latency_multiplier: float = 1.0
    bias_note: str | None = None


class CalibrationResult(ISABaseModel):
    """
    Output of CalibrationAndBiasAdjustmentNode.
    Section 6.1 of the convention.
    """
    enabled_for_existing_system: bool = False
    historical_errors: list[CalibrationError] = Field(default_factory=list)
    safety_buffer: SafetyBuffer = Field(default_factory=SafetyBuffer)
    calibration_notes: list[str] = Field(default_factory=list)

    @property
    def max_cost_delta(self) -> float:
        for e in self.historical_errors:
            if e.metric == "cost":
                return e.delta
        return 0.0

    @property
    def max_latency_delta(self) -> float:
        for e in self.historical_errors:
            if e.metric == "latency":
                return e.delta
        return 0.0

    def apply_buffer_if_needed(self) -> None:
        """Apply +15% safety buffer if historical error delta > 20%."""
        threshold = settings.CALIBRATION_BUFFER_THRESHOLD
        multiplier = settings.SAFETY_BUFFER_MULTIPLIER
        cost_exceeded = self.max_cost_delta > threshold
        latency_exceeded = self.max_latency_delta > threshold

        if cost_exceeded or latency_exceeded:
            self.safety_buffer = SafetyBuffer(
                applied=True,
                reason=(
                    f"Historical forecast delta exceeded {int(threshold * 100)}%; "
                    f"+{round((multiplier - 1) * 100)}% safety buffer applied."
                ),
                cost_multiplier=multiplier if cost_exceeded else 1.0,
                latency_multiplier=multiplier if latency_exceeded else 1.0,
                bias_note=(
                    f"Cost estimate includes +{round((multiplier - 1) * 100)}% safety buffer "
                    "due to prior forecast error >20%."
                    if cost_exceeded
                    else None
                ),
            )
