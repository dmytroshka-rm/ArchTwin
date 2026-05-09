from __future__ import annotations

"""
isa_cad/agent/tools/freshness_check.py
========================================
LangChain tool — check data freshness for a named source.

Returns the age of the data source in hours and whether it is considered
stale according to the configured threshold.  Used by reviewers and the
fidelity gate to decide if estimates can be promoted to FINAL_FORECAST.

Source names map to DataSourceType enum values:
    cloud_inventory | runtime_metrics | pricing_data | calibration_data
"""

import json
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from isa_cad.core.freshness_engine import FreshnessReport


class _FreshnessCheckInput(BaseModel):
    source_name: str = Field(
        ...,
        description=(
            "Name of the data source to check. "
            "One of: cloud_inventory, runtime_metrics, pricing_data, calibration_data"
        ),
    )


class FreshnessCheckTool(BaseTool):
    """
    Check whether a named data source is fresh or stale.

    Reads the ``FreshnessReport`` produced by ``ContextAndFreshnessNode``
    and returns the age and stale flag of the requested source.
    """

    name: str = "freshness_check"
    description: str = (
        "Check the freshness of a data source by name. "
        "Valid names: cloud_inventory, runtime_metrics, pricing_data, calibration_data. "
        "Returns {source_name, age_hours, is_stale, label}. "
        "Use this to decide whether to recommend a graph refresh or flag a fidelity concern."
    )
    args_schema: Type[BaseModel] = _FreshnessCheckInput

    freshness_report: FreshnessReport = Field(default_factory=FreshnessReport)

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, source_name: str) -> str:
        for source in self.freshness_report.sources:
            if source.source_type.value == source_name:
                return json.dumps({
                    "source_name": source_name,
                    "age_hours":   round(source.age_hours, 2),
                    "is_stale":    source.is_stale,
                    "label":       source.label,
                    "freshness_score": round(source.freshness_score, 4),
                })

        return json.dumps({
            "source_name": source_name,
            "age_hours":   None,
            "is_stale":    True,
            "label":       "unknown",
            "freshness_score": 0.0,
            "note": (
                f"Source '{source_name}' not found in the freshness report. "
                "Valid names: cloud_inventory, runtime_metrics, pricing_data, calibration_data."
            ),
        })
