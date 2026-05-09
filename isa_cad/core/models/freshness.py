from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import Field

from .base import ISABaseModel


class DataSourceType(str, Enum):
    CLOUD_INVENTORY = "cloud_inventory"
    RUNTIME_METRICS = "runtime_metrics"
    PRICING_DATA = "pricing_data"
    CALIBRATION_DATA = "calibration_data"


# Convention Section 8 — freshness targets per source
FRESHNESS_TARGETS: dict[DataSourceType, timedelta] = {
    DataSourceType.CLOUD_INVENTORY:  timedelta(hours=24),
    DataSourceType.RUNTIME_METRICS:  timedelta(hours=24),
    DataSourceType.PRICING_DATA:     timedelta(days=7),
    DataSourceType.CALIBRATION_DATA: timedelta(days=90),   # "latest available"
}


class DataSourceFreshness(ISABaseModel):
    """Freshness record for a single data source."""
    source_type: DataSourceType
    collected_at: datetime
    freshness_score: float = Field(0.0, ge=0.0, le=1.0)
    age_hours: float = Field(0.0, ge=0.0)
    is_stale: bool = False
    label: str = ""   # human-readable age string, e.g. "2h", "3d"

    @classmethod
    def compute(
        cls,
        source_type: DataSourceType,
        collected_at: datetime,
        now: datetime | None = None,
    ) -> "DataSourceFreshness":
        """
        Compute freshness_score for a source based on its age vs target window.

        Score = max(0, 1 - age / (2 * target))
          → 1.0 when brand new
          → 0.5 when exactly at target boundary
          → 0.0 when age >= 2 * target (hard floor)

        is_stale = True when age > target (penalty applies to confidence).
        """
        if now is None:
            now = datetime.now(UTC)

        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=UTC)

        target = FRESHNESS_TARGETS[source_type]
        age = now - collected_at
        age_hours = age.total_seconds() / 3600

        score = max(0.0, 1.0 - age.total_seconds() / (2 * target.total_seconds()))
        score = round(score, 4)
        is_stale = age > target

        return cls(
            source_type=source_type,
            collected_at=collected_at,
            freshness_score=score,
            age_hours=round(age_hours, 2),
            is_stale=is_stale,
            label=cls._format_age(age),
        )

    @staticmethod
    def _format_age(age: timedelta) -> str:
        total_seconds = int(age.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 48:
            return f"{hours}h"
        return f"{hours // 24}d"
