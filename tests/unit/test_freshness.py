from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from isa_cad.core.freshness_engine import FreshnessEngine, FreshnessReport
from isa_cad.core.models.enums import OutputMode
from isa_cad.core.models.freshness import (
    DataSourceFreshness,
    DataSourceType,
    FRESHNESS_TARGETS,
)

NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
engine = FreshnessEngine()


# ── DataSourceFreshness.compute ───────────────────────────────────────────────

def test_brand_new_score_is_one():
    dsf = DataSourceFreshness.compute(
        DataSourceType.CLOUD_INVENTORY,
        collected_at=NOW,
        now=NOW,
    )
    assert dsf.freshness_score == 1.0
    assert not dsf.is_stale
    assert dsf.label == "0s"


def test_score_at_target_boundary():
    # age == target (24h for inventory) → score = 1 - 1/(2) = 0.5
    # is_stale uses strictly > so exactly at boundary = NOT stale
    target = FRESHNESS_TARGETS[DataSourceType.CLOUD_INVENTORY]
    collected_at = NOW - target
    dsf = DataSourceFreshness.compute(DataSourceType.CLOUD_INVENTORY, collected_at, now=NOW)
    assert dsf.freshness_score == 0.5
    assert not dsf.is_stale   # age == target → strictly > is False → not stale


def test_stale_when_over_target():
    target = FRESHNESS_TARGETS[DataSourceType.CLOUD_INVENTORY]
    collected_at = NOW - target - timedelta(minutes=1)
    dsf = DataSourceFreshness.compute(DataSourceType.CLOUD_INVENTORY, collected_at, now=NOW)
    assert dsf.is_stale


def test_score_floor_at_zero():
    # age = 3 * target → score = 1 - 3/2 = -0.5 → floored to 0.0
    target = FRESHNESS_TARGETS[DataSourceType.CLOUD_INVENTORY]
    collected_at = NOW - (3 * target)
    dsf = DataSourceFreshness.compute(DataSourceType.CLOUD_INVENTORY, collected_at, now=NOW)
    assert dsf.freshness_score == 0.0


def test_pricing_data_7d_target():
    # pricing target is 7 days → age 3d5h should not be stale
    collected_at = NOW - timedelta(days=3, hours=5)
    dsf = DataSourceFreshness.compute(DataSourceType.PRICING_DATA, collected_at, now=NOW)
    assert not dsf.is_stale
    assert dsf.freshness_score > 0.5


def test_label_formatting():
    cases = [
        (timedelta(seconds=45), "45s"),
        (timedelta(minutes=30), "30m"),
        (timedelta(hours=5), "5h"),
        (timedelta(days=3), "3d"),
    ]
    for age, expected_label in cases:
        dsf = DataSourceFreshness.compute(
            DataSourceType.RUNTIME_METRICS,
            collected_at=NOW - age,
            now=NOW,
        )
        assert dsf.label == expected_label, f"age={age} → expected {expected_label}, got {dsf.label}"


def test_naive_datetime_treated_as_utc():
    naive = datetime(2026, 5, 8, 10, 0, 0)   # no tzinfo
    dsf = DataSourceFreshness.compute(DataSourceType.CLOUD_INVENTORY, naive, now=NOW)
    assert dsf.age_hours == pytest.approx(2.0, abs=0.01)


# ── FreshnessEngine.analyse ───────────────────────────────────────────────────

def test_all_fresh_no_penalty():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=2),
        runtime_metrics_age=timedelta(minutes=5),
        pricing_data_age=timedelta(days=1),
        base_confidence=0.90,
        now=NOW,
    )
    assert report.output_mode == OutputMode.FINAL_FORECAST
    assert report.confidence_penalty == 0.0
    assert report.adjusted_confidence == pytest.approx(report.freshness_score * 0.90, abs=0.01)
    assert not report.require_observed_graph_refresh
    assert report.stale_sources == []


def test_stale_inventory_applies_penalty():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=30),   # > 24h target → stale
        base_confidence=0.90,
        now=NOW,
    )
    assert DataSourceType.CLOUD_INVENTORY.value in report.stale_sources
    assert report.confidence_penalty > 0.0
    assert report.adjusted_confidence < 0.90


def test_freshness_score_is_minimum():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=2),    # fresh → ~0.96
        runtime_metrics_age=timedelta(hours=23),   # near boundary → ~0.52
        base_confidence=1.0,
        now=NOW,
    )
    inv_score = next(
        s.freshness_score for s in report.sources
        if s.source_type == DataSourceType.CLOUD_INVENTORY
    )
    met_score = next(
        s.freshness_score for s in report.sources
        if s.source_type == DataSourceType.RUNTIME_METRICS
    )
    assert report.freshness_score == min(inv_score, met_score)


def test_data_older_than_7d_triggers_exploratory():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(days=8),
        base_confidence=0.80,
        now=NOW,
    )
    assert report.output_mode == OutputMode.EXPLORATORY_ESTIMATE
    assert report.exploratory_reason != ""


def test_low_confidence_triggers_refresh():
    # Very stale data: inventory 48h old → score ~0, penalty 0.10
    # base 0.70 * 0 - 0.10 = -0.10 → 0.0 < MIN_CONFIDENCE → require refresh
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=48),
        runtime_metrics_age=timedelta(hours=48),
        base_confidence=0.70,
        now=NOW,
    )
    assert report.require_observed_graph_refresh


def test_no_refresh_when_confidence_ok():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=1),
        base_confidence=0.95,
        now=NOW,
    )
    assert not report.require_observed_graph_refresh


def test_to_simulation_fidelity():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=2),
        runtime_metrics_age=timedelta(minutes=5),
        base_confidence=0.82,
        now=NOW,
    )
    fidelity = report.to_simulation_fidelity(base_confidence=0.82)
    assert fidelity.base_confidence == 0.82
    assert fidelity.adjusted_confidence == report.adjusted_confidence
    assert fidelity.data_freshness_score == report.freshness_score
    assert fidelity.output_mode == report.output_mode.value
    assert fidelity.data_age.cloud_inventory is not None
    assert fidelity.data_age.runtime_metrics is not None


def test_empty_sources_returns_defaults():
    report = engine.analyse({}, base_confidence=0.90, now=NOW)
    assert report.freshness_score == 1.0
    assert report.output_mode == OutputMode.FINAL_FORECAST
    assert report.adjusted_confidence == pytest.approx(0.90 * 1.0, abs=0.001)


def test_data_age_labels_populated():
    report = engine.analyse_from_ages(
        cloud_inventory_age=timedelta(hours=3),
        pricing_data_age=timedelta(days=2),
        base_confidence=0.85,
        now=NOW,
    )
    age = report.data_age
    assert age.cloud_inventory == "3h"
    assert age.pricing_data == "2d"
    assert age.runtime_metrics is None
