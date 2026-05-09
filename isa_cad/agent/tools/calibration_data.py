from __future__ import annotations

"""
isa_cad/agent/tools/calibration_data.py
=========================================
LangChain tool — retrieve historical calibration stats for a component class.

Returns the mean and worst-case error delta for a given component class
and metric from the CalibrationStore.  Used by reviewers to determine
whether conservative adjustment is warranted before finalising an estimate.
"""

import json
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from isa_cad.core.calibration_store import CalibrationStore


class _CalibrationDataInput(BaseModel):
    component_class: str = Field(
        ...,
        description="Component class to query, e.g. 'database', 'service', 'queue'",
    )
    metric: str = Field(
        ...,
        description="Metric name to query, e.g. 'cost', 'latency'",
    )


class CalibrationDataTool(BaseTool):
    """
    Retrieve historical calibration error statistics for a component class + metric.

    Returns:
        record_count   — number of matched calibration entries
        mean_error     — mean error_delta across matched entries
        worst_error    — worst-case (max) error_delta
        bias_direction — "over" | "under" | "none"

    Use this to decide whether to apply a conservative safety buffer to
    numerical estimates for cost or latency.
    """

    name: str = "calibration_data"
    description: str = (
        "Retrieve historical calibration error stats for a component class and metric. "
        "Returns {record_count, mean_error, worst_error, bias_direction}. "
        "Use this to decide whether to apply a conservative safety buffer "
        "to numerical estimates for cost or latency."
    )
    args_schema: Type[BaseModel] = _CalibrationDataInput

    store: CalibrationStore = Field(default_factory=CalibrationStore)

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, component_class: str, metric: str) -> str:
        deltas: list[float] = []
        for entry in self.store.iter_entries():
            if (entry.forecast.component_class == component_class
                    and entry.forecast.metric == metric):
                deltas.append(entry.error_delta)

        if not deltas:
            return json.dumps({
                "component_class": component_class,
                "metric":          metric,
                "record_count":    0,
                "mean_error":      None,
                "worst_error":     None,
                "bias_direction":  "unknown",
                "note": "No calibration history found for this component class + metric.",
            })

        mean  = round(sum(deltas) / len(deltas), 6)
        worst = round(max(deltas), 6)
        bias  = "over" if mean > 0 else "under" if mean < 0 else "none"

        return json.dumps({
            "component_class": component_class,
            "metric":          metric,
            "record_count":    len(deltas),
            "mean_error":      mean,
            "worst_error":     worst,
            "bias_direction":  bias,
        })
