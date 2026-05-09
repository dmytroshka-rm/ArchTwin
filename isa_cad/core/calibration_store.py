from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from isa_cad.config.settings import settings
from isa_cad.core.models.calibration import CalibrationError, CalibrationResult, SafetyBuffer
from isa_cad.core.models.calibration_record import ActualRecord, CalibrationEntry, ForecastRecord


class CalibrationStore:
    """
    File-based store for forecast/actual calibration records.

    Layout on disk:
        <base_dir>/
            forecasts/<id>.json
            actuals/<forecast_id>/<id>.json
            entries/<forecast_id>.json   ← matched CalibrationEntry

    The store is used by CalibrationAndBiasAdjustmentNode (Phase 5.2)
    to query historical error deltas per component_class and metric.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or (settings.CHECKPOINT_DIR / "calibration")
        for sub in ("forecasts", "actuals", "entries"):
            (self._base / sub).mkdir(parents=True, exist_ok=True)

    # ── forecasts ────────────────────────────────────────────────────────────

    def save_forecast(self, record: ForecastRecord) -> Path:
        path = self._base / "forecasts" / f"{_safe(record.id)}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_forecast(self, forecast_id: str) -> ForecastRecord | None:
        path = self._base / "forecasts" / f"{_safe(forecast_id)}.json"
        if not path.exists():
            return None
        return ForecastRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list_forecast_ids(self) -> list[str]:
        return [p.stem for p in (self._base / "forecasts").glob("*.json")]

    # ── actuals ───────────────────────────────────────────────────────────────

    def save_actual(self, record: ActualRecord) -> Path:
        sub = self._base / "actuals" / _safe(record.forecast_id)
        sub.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        path = sub / f"{ts}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_actuals_for_forecast(self, forecast_id: str) -> list[ActualRecord]:
        sub = self._base / "actuals" / _safe(forecast_id)
        if not sub.exists():
            return []
        records = []
        for p in sub.glob("*.json"):
            records.append(ActualRecord.model_validate(json.loads(p.read_text(encoding="utf-8"))))
        records.sort(key=lambda r: r.observed_at)
        return records

    # ── entries (matched pairs) ───────────────────────────────────────────────

    def save_entry(self, entry: CalibrationEntry) -> Path:
        path = self._base / "entries" / f"{_safe(entry.forecast.id)}.json"
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_entry(self, forecast_id: str) -> CalibrationEntry | None:
        path = self._base / "entries" / f"{_safe(forecast_id)}.json"
        if not path.exists():
            return None
        return CalibrationEntry.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def iter_entries(self) -> Iterator[CalibrationEntry]:
        for p in (self._base / "entries").glob("*.json"):
            yield CalibrationEntry.model_validate(json.loads(p.read_text(encoding="utf-8")))

    # ── matching: record actual against latest forecast ───────────────────────

    def record_actual_and_match(
        self,
        forecast_id: str,
        actual_value: float,
        unit: str = "",
        source: str = "",
        notes: str = "",
    ) -> CalibrationEntry | None:
        """
        Save an ActualRecord and build (or update) the CalibrationEntry.
        Returns the entry, or None if the forecast is not found.
        """
        forecast = self.load_forecast(forecast_id)
        if forecast is None:
            return None

        actual = ActualRecord(
            forecast_id=forecast_id,
            actual_value=actual_value,
            unit=unit,
            source=source,
            notes=notes,
        )
        self.save_actual(actual)

        entry = CalibrationEntry(forecast=forecast, actual=actual)
        self.save_entry(entry)
        return entry

    # ── query: compute CalibrationResult for a component class ───────────────

    def build_calibration_result(
        self,
        component_class: str,
        metrics: list[str] | None = None,
    ) -> CalibrationResult:
        """
        Aggregate all CalibrationEntries for a given component_class
        and return a CalibrationResult with the worst-case error deltas.

        Used by CalibrationAndBiasAdjustmentNode before applying Safety Buffer.
        """
        if metrics is None:
            metrics = ["cost", "latency"]

        worst: dict[str, float] = {}

        for entry in self.iter_entries():
            if entry.forecast.component_class != component_class:
                continue
            metric = entry.forecast.metric
            if metric not in metrics:
                continue
            if entry.error_delta > worst.get(metric, 0.0):
                worst[metric] = entry.error_delta

        errors = [
            CalibrationError(
                metric=m,
                predicted_value=1.0 + delta,   # synthetic: keeps ratio correct
                actual_value=1.0,
            )
            for m, delta in worst.items()
        ]

        result = CalibrationResult(
            enabled_for_existing_system=bool(errors),
            historical_errors=errors,
        )
        result.apply_buffer_if_needed()
        return result

    # ── stats ─────────────────────────────────────────────────────────────────

    def component_class_stats(self) -> dict[str, dict[str, float]]:
        """
        Return {component_class: {metric: avg_error_delta}} across all entries.
        Useful for diagnostics and reporting.
        """
        totals: dict[str, dict[str, list[float]]] = {}
        for entry in self.iter_entries():
            cc = entry.forecast.component_class
            m = entry.forecast.metric
            totals.setdefault(cc, {}).setdefault(m, []).append(entry.error_delta)

        return {
            cc: {m: round(sum(vals) / len(vals), 4) for m, vals in metrics.items()}
            for cc, metrics in totals.items()
        }


def _safe(s: str) -> str:
    """Make a string safe to use as a filename."""
    return s.replace("/", "_").replace("\\", "_").replace(":", "-").replace(" ", "_")
