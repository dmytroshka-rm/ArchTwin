from __future__ import annotations

from pydantic import Field

from .base import EvidenceRef, ISABaseModel
from .enums import ReviewerStatus, ReviewerType
from .veto import VetoGate


class Finding(ISABaseModel):
    """A specific finding from a reviewer."""
    severity: str = Field(..., description="critical | high | medium | low | info")
    title: str
    description: str
    recommendation: str | None = None


class ReviewerOutput(ISABaseModel):
    """
    Output contract for each parallel reviewer.
    Sections 5 and 0.1 of the convention.
    """
    reviewer: ReviewerType
    status: ReviewerStatus = Field(ReviewerStatus.UNKNOWN)
    score: float = Field(0.0, ge=0.0, le=1.0)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    veto_gates: list[VetoGate] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendation: str = Field("")

    @property
    def has_critical_fail(self) -> bool:
        return self.status == ReviewerStatus.FAIL and any(
            g.is_blocking for g in self.veto_gates
        )


class CostReviewerOutput(ReviewerOutput):
    """Extended output for CostReviewer."""
    reviewer: ReviewerType = ReviewerType.COST
    monthly_current_usd: float | None = None
    monthly_projected_usd: float | None = None
    egress_monthly_usd: float | None = None
    cache_hit_ratio: float | None = None
    cache_hit_ratio_source: str | None = None
    inter_region_cost_usd: float | None = None
    request_fees_usd: float | None = None
    tco_delta_usd: float | None = None


class PerformanceReviewerOutput(ReviewerOutput):
    """Extended output for PerformanceReviewer."""
    reviewer: ReviewerType = ReviewerType.PERFORMANCE
    latency_delta: str | None = None
    p95_baseline_ms: float | None = None
    p95_projected_ms: float | None = None
    p99_baseline_ms: float | None = None
    p99_projected_ms: float | None = None
    throughput_rps: float | None = None
    bottleneck_risk: str | None = None       # low | medium | high
    cold_start_risk: str | None = None
    db_pressure_risk: str | None = None
    queue_pressure_risk: str | None = None


class SecurityReviewerOutput(ReviewerOutput):
    """Extended output for SecurityReviewer."""
    reviewer: ReviewerType = ReviewerType.SECURITY
    public_exposure_risk: str | None = None
    iam_scope_risk: str | None = None
    trust_boundary_violations: list[str] = Field(default_factory=list)
    pii_flow_status: str = Field("unknown")      # pass | fail | warning | unknown
    data_residency_status: str = Field("unknown")
    compliance_status: str = Field("unknown")
