from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, field_validator

from .base import ISABaseModel


class ForecastRecord(ISABaseModel):
    """
    A single forecast made by the agent for a specific component and metric.
    Stored before implementation so it can be compared against actuals later.
    Section 6.1 — Self-Calibration Loop.
    """
    id: str = Field(..., description="Unique record ID, e.g. 'forecast.orders-api.cost.2026-05-08'")
    proposal_id: str = Field(..., description="DesignProposal.id this forecast belongs to")
    component_class: str = Field(
        ...,
        description="Component pattern for matching future forecasts, e.g. 'lambda', 'ecs', 'rds'",
    )
    metric: str = Field(..., description="'cost' | 'latency' | 'blast_radius_components'")
    predicted_value: float
    unit: str = Field("", description="e.g. 'usd/month', 'ms', 'count'")
    forecasted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context_notes: list[str] = Field(default_factory=list)

    @field_validator("id", "proposal_id", "component_class", "metric")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be empty")
        return v


class ActualRecord(ISABaseModel):
    """
    The observed actual value after a proposal was implemented.
    Linked to a ForecastRecord by forecast_id.
    """
    forecast_id: str
    actual_value: float
    unit: str = Field("")
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = Field("", description="How the actual was captured, e.g. 'aws_cost_explorer'")
    notes: str = ""


class CalibrationEntry(ISABaseModel):
    """
    A matched pair: forecast + actual + computed error delta.
    Used by CalibrationNode to decide if Safety Buffer is needed.

    historical_error_delta = ABS(predicted - actual) / actual  (Section 6.1)
    """
    forecast: ForecastRecord
    actual: ActualRecord
    error_delta: float = Field(0.0, ge=0.0, description="ABS(predicted-actual)/actual")
    buffer_triggered: bool = False

    def model_post_init(self, __context: object) -> None:
        if self.actual.actual_value != 0:
            delta = abs(self.forecast.predicted_value - self.actual.actual_value) / abs(
                self.actual.actual_value
            )
            object.__setattr__(self, "error_delta", round(delta, 4))
