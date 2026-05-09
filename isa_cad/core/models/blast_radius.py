from __future__ import annotations

from pydantic import Field, field_validator

from .base import ISABaseModel
from .enums import ComponentTier
from isa_cad.config.settings import settings


class ImpactedComponent(ISABaseModel):
    """
    A stable component impacted by a design change.
    Formula: impact_score = (base_impact * C_m) * 0.5 ** (d - 1)
    """
    id: str = Field(..., description="Component identifier, e.g. 'component.postgresql.shared-db'")
    tier: ComponentTier
    distance: int = Field(..., ge=1, description="Graph distance from edited component (d)")
    criticality_multiplier: float = Field(..., gt=0.0, description="C_m based on tier")
    impact_score: float = Field(..., ge=0.0, description="Computed impact score")
    risk: str = Field(..., description="Short risk description")
    mitigations: list[str] = Field(default_factory=list)

    @field_validator("criticality_multiplier", mode="before")
    @classmethod
    def validate_multiplier(cls, v: float) -> float:
        allowed = {
            settings.CRITICALITY_TIER_1,
            settings.CRITICALITY_STANDARD,
            settings.CRITICALITY_AUXILIARY,
        }
        if v not in allowed:
            raise ValueError(f"criticality_multiplier must be one of {allowed}, got {v}")
        return v

    @classmethod
    def from_tier(
        cls,
        id: str,
        tier: ComponentTier,
        distance: int,
        base_impact: float,
        risk: str,
        mitigations: list[str] | None = None,
    ) -> "ImpactedComponent":
        """Factory: compute criticality_multiplier and impact_score from tier and distance."""
        tier_map = {
            ComponentTier.TIER_1: settings.CRITICALITY_TIER_1,
            ComponentTier.STANDARD: settings.CRITICALITY_STANDARD,
            ComponentTier.AUXILIARY: settings.CRITICALITY_AUXILIARY,
        }
        c_m = tier_map[tier]
        impact_score = (base_impact * c_m) * (0.5 ** (distance - 1))
        return cls(
            id=id,
            tier=tier,
            distance=distance,
            criticality_multiplier=c_m,
            impact_score=round(impact_score, 4),
            risk=risk,
            mitigations=mitigations or [],
        )


class BlastRadiusOutput(ISABaseModel):
    """
    Output of BlastRadiusNode — tier-aware impact traversal.
    Section 9 of the convention.
    """
    source_component_id: str = Field(..., description="The component being modified")
    max_traversal_depth: int = Field(3, ge=1, description="How deep the graph was traversed")
    impacted_stable_components: list[ImpactedComponent] = Field(default_factory=list)
    total_impact_score: float = Field(0.0, ge=0.0)
    high_risk_count: int = Field(0, ge=0)
    summary: str = Field("")

    def model_post_init(self, __context: object) -> None:
        object.__setattr__(
            self,
            "total_impact_score",
            round(sum(c.impact_score for c in self.impacted_stable_components), 4),
        )
        object.__setattr__(
            self,
            "high_risk_count",
            sum(
                1
                for c in self.impacted_stable_components
                if c.tier == ComponentTier.TIER_1 and c.impact_score >= 1.0
            ),
        )
