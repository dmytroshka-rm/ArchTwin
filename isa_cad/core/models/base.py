from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ISABaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )


class EvidenceRef(ISABaseModel):
    """Reference to a piece of evidence used in analysis."""
    source: str = Field(..., description="Source identifier (e.g. 'aws_pricing_api', 'observed_metrics')")
    description: str = Field(..., description="Human-readable description of the evidence")
    value: Any = Field(None, description="Numeric or structured value if applicable")
    collected_at: datetime | None = Field(None, description="When this evidence was collected")
    is_assumption: bool = Field(False, description="True if this is a heuristic/assumption, not observed data")


class DataAge(ISABaseModel):
    """Tracks freshness of different data sources."""
    cloud_inventory: str | None = Field(None, description="e.g. '2h', '1d'")
    runtime_metrics: str | None = Field(None, description="e.g. '5m', '3h'")
    pricing_data: str | None = Field(None, description="e.g. '1d', '6d'")
    calibration_data: str | None = Field(None, description="e.g. 'latest', '30d'")


class SimulationFidelity(ISABaseModel):
    """Tracks confidence and data freshness for a simulation."""
    base_confidence: float = Field(..., ge=0.0, le=1.0)
    data_freshness_score: float = Field(..., ge=0.0, le=1.0)
    confidence_penalty: float = Field(0.0, ge=0.0, le=1.0)
    adjusted_confidence: float = Field(..., ge=0.0, le=1.0)
    data_age: DataAge = Field(default_factory=DataAge)
    output_mode: str = Field("final_forecast")
    require_observed_graph_refresh: bool = Field(False)
