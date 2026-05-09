from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field

from isa_cad.config.settings import settings
from isa_cad.core.models.base import DataAge, SimulationFidelity
from isa_cad.core.models.enums import OutputMode
from isa_cad.core.models.freshness import DataSourceFreshness, DataSourceType, FRESHNESS_TARGETS


@dataclass
class FreshnessReport:
    """
    Full freshness analysis for all data sources in a simulation.
    Section 8 of the convention.

    freshness_score = min(source_freshness_scores)
    adjusted_confidence = base_confidence * freshness_score - confidence_penalty
    """
    sources: list[DataSourceFreshness] = field(default_factory=list)
    freshness_score: float = 1.0
    confidence_penalty: float = 0.0
    adjusted_confidence: float = 1.0
    output_mode: OutputMode = OutputMode.FINAL_FORECAST
    require_observed_graph_refresh: bool = False
    stale_sources: list[str] = field(default_factory=list)
    exploratory_reason: str = ""

    @property
    def data_age(self) -> DataAge:
        """Build a DataAge object from computed source labels."""
        labels: dict[str, str] = {s.source_type.value: s.label for s in self.sources}
        return DataAge(
            cloud_inventory=labels.get(DataSourceType.CLOUD_INVENTORY.value),
            runtime_metrics=labels.get(DataSourceType.RUNTIME_METRICS.value),
            pricing_data=labels.get(DataSourceType.PRICING_DATA.value),
            calibration_data=labels.get(DataSourceType.CALIBRATION_DATA.value),
        )

    def to_simulation_fidelity(self, base_confidence: float) -> SimulationFidelity:
        return SimulationFidelity(
            base_confidence=round(base_confidence, 4),
            data_freshness_score=round(self.freshness_score, 4),
            confidence_penalty=round(self.confidence_penalty, 4),
            adjusted_confidence=round(self.adjusted_confidence, 4),
            data_age=self.data_age,
            output_mode=self.output_mode.value,
            require_observed_graph_refresh=self.require_observed_graph_refresh,
        )


class FreshnessEngine:
    """
    Computes data freshness scores and confidence adjustments.
    Implements the rules from Section 8 of the convention.

    Rules:
      1. freshness_score = min(all source scores)
      2. adjusted_confidence = base_confidence * freshness_score − confidence_penalty
      3. if any source age > 7 days → output_mode = exploratory_estimate
      4. if adjusted_confidence < MIN_CONFIDENCE due to stale data →
           require_observed_graph_refresh = True
    """

    # Confidence penalty per stale source type
    _STALE_PENALTIES: dict[DataSourceType, float] = {
        DataSourceType.CLOUD_INVENTORY: 0.10,
        DataSourceType.RUNTIME_METRICS: 0.10,
        DataSourceType.PRICING_DATA:    0.05,
        DataSourceType.CALIBRATION_DATA: 0.03,
    }

    def analyse(
        self,
        collected_at_map: dict[DataSourceType, datetime],
        base_confidence: float,
        now: datetime | None = None,
    ) -> FreshnessReport:
        """
        Run freshness analysis for the provided data sources.

        Args:
            collected_at_map: {DataSourceType → datetime when data was collected}
            base_confidence:  reviewer's raw confidence before freshness adjustment
            now:              override for "current time" (useful in tests)
        """
        if now is None:
            now = datetime.now(UTC)

        sources: list[DataSourceFreshness] = []
        stale_sources: list[str] = []
        confidence_penalty = 0.0
        exploratory_reason = ""

        for source_type, collected_at in collected_at_map.items():
            dsf = DataSourceFreshness.compute(source_type, collected_at, now=now)
            sources.append(dsf)
            if dsf.is_stale:
                stale_sources.append(source_type.value)
                confidence_penalty += self._STALE_PENALTIES.get(source_type, 0.05)

        # freshness_score = min of all source scores (Section 8)
        freshness_score = min((s.freshness_score for s in sources), default=1.0)

        # adjusted_confidence = base * freshness - penalty (floor at 0)
        adjusted_confidence = max(
            0.0,
            round(base_confidence * freshness_score - confidence_penalty, 4),
        )

        # Exploratory mode: any source older than STALE_DATA_DAYS
        stale_threshold = timedelta(days=settings.STALE_DATA_DAYS)
        output_mode = OutputMode.FINAL_FORECAST
        for dsf in sources:
            if dsf.age_hours > stale_threshold.total_seconds() / 3600:
                output_mode = OutputMode.EXPLORATORY_ESTIMATE
                exploratory_reason = (
                    f"Source '{dsf.source_type.value}' is {dsf.label} old "
                    f"(>{settings.STALE_DATA_DAYS}d threshold). "
                    "All outputs are exploratory estimates."
                )
                break

        # Require refresh if confidence dropped below minimum
        require_refresh = (
            adjusted_confidence < settings.MIN_CONFIDENCE and len(stale_sources) > 0
        )

        return FreshnessReport(
            sources=sources,
            freshness_score=round(freshness_score, 4),
            confidence_penalty=round(min(confidence_penalty, base_confidence), 4),
            adjusted_confidence=adjusted_confidence,
            output_mode=output_mode,
            require_observed_graph_refresh=require_refresh,
            stale_sources=stale_sources,
            exploratory_reason=exploratory_reason,
        )

    def analyse_from_ages(
        self,
        cloud_inventory_age: timedelta | None = None,
        runtime_metrics_age: timedelta | None = None,
        pricing_data_age: timedelta | None = None,
        calibration_data_age: timedelta | None = None,
        base_confidence: float = 1.0,
        now: datetime | None = None,
    ) -> FreshnessReport:
        """
        Convenience wrapper: pass ages directly as timedeltas.
        Useful in tests and when the agent only knows how old data is.
        """
        if now is None:
            now = datetime.now(UTC)

        age_map: dict[DataSourceType, timedelta] = {}
        if cloud_inventory_age is not None:
            age_map[DataSourceType.CLOUD_INVENTORY] = cloud_inventory_age
        if runtime_metrics_age is not None:
            age_map[DataSourceType.RUNTIME_METRICS] = runtime_metrics_age
        if pricing_data_age is not None:
            age_map[DataSourceType.PRICING_DATA] = pricing_data_age
        if calibration_data_age is not None:
            age_map[DataSourceType.CALIBRATION_DATA] = calibration_data_age

        collected_at_map = {
            src: now - age for src, age in age_map.items()
        }
        return self.analyse(collected_at_map, base_confidence=base_confidence, now=now)
