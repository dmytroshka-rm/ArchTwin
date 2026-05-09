from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from isa_cad.core.calibration_store import CalibrationStore
from isa_cad.core.models.calibration_record import ActualRecord, CalibrationEntry, ForecastRecord


# ── helpers ───────────────────────────────────────────────────────────────────

def make_forecast(
    fid: str = "forecast.orders-api.cost.001",
    component_class: str = "lambda",
    metric: str = "cost",
    predicted: float = 1000.0,
) -> ForecastRecord:
    return ForecastRecord(
        id=fid,
        proposal_id="proposal.layer-a",
        component_class=component_class,
        metric=metric,
        predicted_value=predicted,
        unit="usd/month",
    )


# ── ForecastRecord validation ─────────────────────────────────────────────────

def test_forecast_empty_id_raises():
    with pytest.raises(ValueError):
        ForecastRecord(id="", proposal_id="p", component_class="lambda", metric="cost", predicted_value=100)


def test_forecast_empty_metric_raises():
    with pytest.raises(ValueError):
        ForecastRecord(id="f1", proposal_id="p", component_class="lambda", metric="  ", predicted_value=100)


# ── CalibrationEntry error_delta ─────────────────────────────────────────────

def test_entry_error_delta_correct():
    forecast = make_forecast(predicted=1200)
    actual = ActualRecord(forecast_id=forecast.id, actual_value=1000)
    entry = CalibrationEntry(forecast=forecast, actual=actual)
    # |1200 - 1000| / 1000 = 0.20
    assert entry.error_delta == pytest.approx(0.20, abs=0.0001)


def test_entry_error_delta_zero_actual():
    forecast = make_forecast(predicted=100)
    actual = ActualRecord(forecast_id=forecast.id, actual_value=0)
    entry = CalibrationEntry(forecast=forecast, actual=actual)
    assert entry.error_delta == 0.0   # no division by zero


def test_entry_error_delta_underestimate():
    forecast = make_forecast(predicted=800)
    actual = ActualRecord(forecast_id=forecast.id, actual_value=1000)
    entry = CalibrationEntry(forecast=forecast, actual=actual)
    assert entry.error_delta == pytest.approx(0.20, abs=0.0001)


# ── CalibrationStore CRUD ─────────────────────────────────────────────────────

def test_save_and_load_forecast(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    forecast = make_forecast()
    store.save_forecast(forecast)
    loaded = store.load_forecast(forecast.id)
    assert loaded is not None
    assert loaded.id == forecast.id
    assert loaded.predicted_value == forecast.predicted_value


def test_load_nonexistent_forecast(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    assert store.load_forecast("nonexistent") is None


def test_list_forecast_ids(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    store.save_forecast(make_forecast("f1"))
    store.save_forecast(make_forecast("f2"))
    ids = store.list_forecast_ids()
    assert "f1" in ids and "f2" in ids


def test_save_and_load_actuals(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    forecast = make_forecast()
    store.save_forecast(forecast)

    a1 = ActualRecord(forecast_id=forecast.id, actual_value=950)
    a2 = ActualRecord(forecast_id=forecast.id, actual_value=980)
    store.save_actual(a1)
    store.save_actual(a2)

    actuals = store.load_actuals_for_forecast(forecast.id)
    assert len(actuals) == 2
    assert actuals[0].observed_at <= actuals[1].observed_at  # sorted


def test_load_actuals_nonexistent_forecast(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    assert store.load_actuals_for_forecast("ghost") == []


def test_record_actual_and_match(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    forecast = make_forecast(predicted=1200)
    store.save_forecast(forecast)

    entry = store.record_actual_and_match(
        forecast_id=forecast.id,
        actual_value=1000,
        source="aws_cost_explorer",
    )
    assert entry is not None
    assert entry.error_delta == pytest.approx(0.20, abs=0.0001)
    assert entry.forecast.id == forecast.id


def test_record_actual_nonexistent_forecast(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    result = store.record_actual_and_match("ghost-forecast", 1000)
    assert result is None


def test_save_and_load_entry(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    forecast = make_forecast(predicted=1210)
    actual = ActualRecord(forecast_id=forecast.id, actual_value=1000)
    entry = CalibrationEntry(forecast=forecast, actual=actual)
    store.save_entry(entry)

    loaded = store.load_entry(forecast.id)
    assert loaded is not None
    assert loaded.error_delta == pytest.approx(0.21, abs=0.0001)


# ── CalibrationResult aggregation ────────────────────────────────────────────

def test_build_calibration_result_no_entries(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    result = store.build_calibration_result("lambda")
    assert not result.enabled_for_existing_system
    assert not result.safety_buffer.applied


def test_build_calibration_result_below_threshold(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    # delta = 0.10 → below 20% threshold → no buffer
    f = make_forecast(fid="f-low", predicted=1100)
    store.save_forecast(f)
    store.record_actual_and_match(f.id, actual_value=1000)

    result = store.build_calibration_result("lambda")
    assert result.enabled_for_existing_system
    assert not result.safety_buffer.applied


def test_build_calibration_result_above_threshold(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    # delta = 0.24 → above 20% threshold → buffer applied
    f = make_forecast(fid="f-high", predicted=1240)
    store.save_forecast(f)
    store.record_actual_and_match(f.id, actual_value=1000)

    result = store.build_calibration_result("lambda")
    assert result.safety_buffer.applied
    assert result.safety_buffer.cost_multiplier == 1.15


def test_build_calibration_result_worst_case_wins(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    # Two forecasts for same component; worst one must dominate
    f1 = make_forecast(fid="f-ok",  predicted=1050)  # delta 0.05
    f2 = make_forecast(fid="f-bad", predicted=1300)  # delta 0.30

    store.save_forecast(f1)
    store.save_forecast(f2)
    store.record_actual_and_match(f1.id, actual_value=1000)
    store.record_actual_and_match(f2.id, actual_value=1000)

    result = store.build_calibration_result("lambda")
    assert result.safety_buffer.applied
    assert result.max_cost_delta == pytest.approx(0.30, abs=0.0001)


def test_component_class_stats(tmp_path: Path):
    store = CalibrationStore(base_dir=tmp_path)
    f1 = make_forecast(fid="f-cost",    component_class="ecs", metric="cost",    predicted=1200)
    f2 = make_forecast(fid="f-latency", component_class="ecs", metric="latency", predicted=120)

    store.save_forecast(f1)
    store.save_forecast(f2)
    store.record_actual_and_match(f1.id, actual_value=1000)  # delta 0.20
    store.record_actual_and_match(f2.id, actual_value=100)   # delta 0.20

    stats = store.component_class_stats()
    assert "ecs" in stats
    assert "cost" in stats["ecs"]
    assert "latency" in stats["ecs"]
    assert stats["ecs"]["cost"] == pytest.approx(0.20, abs=0.0001)
