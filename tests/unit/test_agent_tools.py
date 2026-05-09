from __future__ import annotations

"""
tests/unit/test_agent_tools.py
================================
Unit tests for all five LangChain tools in isa_cad/agent/tools/.

Tests are grouped by tool and cover:
  - BaseTool protocol (name, description, args_schema)
  - _run() output is valid JSON
  - Correct data extraction from injected fixtures
  - Graceful handling of missing / empty data
"""

import json
import tempfile
from pathlib import Path

import pytest

from isa_cad.agent.tools import (
    CalibrationDataTool,
    ComponentLookupTool,
    FreshnessCheckTool,
    GraphTraversalTool,
    SchemaValidationTool,
)
from isa_cad.core.calibration_store import CalibrationStore
from isa_cad.core.freshness_engine import FreshnessReport
from isa_cad.core.models.calibration_record import ActualRecord, ForecastRecord
from isa_cad.core.models.freshness import DataSourceFreshness, DataSourceType
from isa_cad.state.canvas_state import (
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
)


# ── shared graph fixture ──────────────────────────────────────────────────────

def _graph() -> ComponentGraph:
    return ComponentGraph(
        nodes=[
            ComponentNode(id="api",  label="API Gateway",  tier="standard",
                          component_type="gateway"),
            ComponentNode(id="svc",  label="Auth Service", tier="standard",
                          component_type="service",
                          metadata={"owner": "platform-team"}),
            ComponentNode(id="db",   label="User DB",      tier="tier_1",
                          component_type="database"),
            ComponentNode(id="cache", label="Redis Cache", tier="auxiliary",
                          component_type="service"),
        ],
        edges=[
            ComponentEdge(source_id="api",  target_id="svc"),
            ComponentEdge(source_id="svc",  target_id="db"),
            ComponentEdge(source_id="svc",  target_id="cache"),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# GraphTraversalTool
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphTraversalTool:

    @pytest.fixture
    def tool(self) -> GraphTraversalTool:
        return GraphTraversalTool(resolved_graph=_graph())

    # ── Protocol ──────────────────────────────────────────────────────────────

    def test_name(self, tool):
        assert tool.name == "graph_traversal"

    def test_description_not_empty(self, tool):
        assert len(tool.description) > 20

    def test_args_schema_has_source_id(self, tool):
        assert "source_id" in tool.args_schema.model_fields

    # ── _run() ────────────────────────────────────────────────────────────────

    def test_returns_valid_json(self, tool):
        result = tool._run(source_id="api")
        doc = json.loads(result)
        assert isinstance(doc, dict)

    def test_reachable_from_api(self, tool):
        doc = json.loads(tool._run(source_id="api", max_depth=3))
        assert "reachable" in doc
        assert "svc" in doc["reachable"]

    def test_distance_api_to_db_is_2(self, tool):
        doc = json.loads(tool._run(source_id="api", max_depth=3))
        assert doc["reachable"]["db"] == 2

    def test_max_depth_1_stops_at_svc(self, tool):
        doc = json.loads(tool._run(source_id="api", max_depth=1))
        assert "svc" in doc["reachable"]
        assert "db" not in doc["reachable"]

    def test_unknown_source_no_crash(self, tool):
        doc = json.loads(tool._run(source_id="ghost"))
        assert doc["reachable"] == {}
        assert "note" in doc

    def test_total_reachable_count(self, tool):
        doc = json.loads(tool._run(source_id="api", max_depth=5))
        assert doc["total_reachable"] == len(doc["reachable"])


# ══════════════════════════════════════════════════════════════════════════════
# ComponentLookupTool
# ══════════════════════════════════════════════════════════════════════════════

class TestComponentLookupTool:

    @pytest.fixture
    def tool(self) -> ComponentLookupTool:
        return ComponentLookupTool(resolved_graph=_graph())

    def test_name(self, tool):
        assert tool.name == "component_lookup"

    def test_found_true_for_existing(self, tool):
        doc = json.loads(tool._run(component_id="api"))
        assert doc["found"] is True

    def test_label_returned(self, tool):
        doc = json.loads(tool._run(component_id="api"))
        assert doc["label"] == "API Gateway"

    def test_tier_returned(self, tool):
        doc = json.loads(tool._run(component_id="db"))
        assert doc["tier"] == "tier_1"

    def test_component_type_returned(self, tool):
        doc = json.loads(tool._run(component_id="db"))
        assert doc["component_type"] == "database"

    def test_metadata_returned(self, tool):
        doc = json.loads(tool._run(component_id="svc"))
        assert doc["metadata"]["owner"] == "platform-team"

    def test_found_false_for_unknown(self, tool):
        doc = json.loads(tool._run(component_id="nonexistent"))
        assert doc["found"] is False
        assert "error" in doc

    def test_returns_valid_json(self, tool):
        result = tool._run(component_id="cache")
        doc = json.loads(result)
        assert isinstance(doc, dict)


# ══════════════════════════════════════════════════════════════════════════════
# SchemaValidationTool
# ══════════════════════════════════════════════════════════════════════════════

class TestSchemaValidationTool:

    @pytest.fixture
    def tool(self) -> SchemaValidationTool:
        return SchemaValidationTool()

    def test_name(self, tool):
        assert tool.name == "schema_validation"

    def test_valid_minimal_proposal(self, tool):
        proposal = {
            "id": "proposal.test",
            "title": "Test",
            "baseline_ref": "arch.prod",
            "optimization_goal": "balanced",
            "status": "sandbox_layer",
        }
        doc = json.loads(tool._run(json.dumps(proposal)))
        assert doc["valid"] is True
        assert doc["error_count"] == 0

    def test_invalid_json_returns_error(self, tool):
        doc = json.loads(tool._run("not json {{{"))
        assert doc["valid"] is False
        assert doc["error_count"] >= 1

    def test_non_dict_returns_error(self, tool):
        doc = json.loads(tool._run(json.dumps([1, 2, 3])))
        assert doc["valid"] is False

    def test_invalid_proposal_reports_errors(self, tool):
        # missing required 'status' field
        proposal = {"id": "p1", "title": "No Status", "baseline_ref": "b",
                    "optimization_goal": "balanced"}
        doc = json.loads(tool._run(json.dumps(proposal)))
        assert doc["valid"] is False
        assert doc["error_count"] >= 1

    def test_returns_valid_json(self, tool):
        result = tool._run(json.dumps({"id": "p1", "title": "t", "baseline_ref": "b",
                                       "optimization_goal": "balanced",
                                       "status": "sandbox_layer"}))
        assert isinstance(json.loads(result), dict)


# ══════════════════════════════════════════════════════════════════════════════
# CalibrationDataTool
# ══════════════════════════════════════════════════════════════════════════════

class TestCalibrationDataTool:

    @pytest.fixture
    def store_with_data(self, tmp_path: Path) -> CalibrationStore:
        store = CalibrationStore(base_dir=tmp_path)
        forecast = ForecastRecord(
            id="f-001",
            proposal_id="p-001",
            component_class="database",
            metric="cost",
            predicted_value=100.0,
        )
        store.save_forecast(forecast)
        store.record_actual_and_match(
            forecast_id="f-001",
            actual_value=120.0,
        )
        return store

    @pytest.fixture
    def tool_with_data(self, store_with_data) -> CalibrationDataTool:
        return CalibrationDataTool(store=store_with_data)

    @pytest.fixture
    def empty_tool(self, tmp_path: Path) -> CalibrationDataTool:
        return CalibrationDataTool(store=CalibrationStore(base_dir=tmp_path))

    def test_name(self, empty_tool):
        assert empty_tool.name == "calibration_data"

    def test_returns_valid_json(self, tool_with_data):
        result = tool_with_data._run("database", "cost")
        assert isinstance(json.loads(result), dict)

    def test_record_count_populated(self, tool_with_data):
        doc = json.loads(tool_with_data._run("database", "cost"))
        assert doc["record_count"] == 1

    def test_mean_error_positive(self, tool_with_data):
        doc = json.loads(tool_with_data._run("database", "cost"))
        # actual > predicted → positive error_delta
        assert doc["mean_error"] > 0

    def test_bias_over_when_positive(self, tool_with_data):
        doc = json.loads(tool_with_data._run("database", "cost"))
        assert doc["bias_direction"] == "over"

    def test_no_records_returns_zero_count(self, empty_tool):
        doc = json.loads(empty_tool._run("lambda", "latency"))
        assert doc["record_count"] == 0
        assert doc["mean_error"] is None
        assert "note" in doc

    def test_wrong_class_no_records(self, tool_with_data):
        doc = json.loads(tool_with_data._run("queue", "cost"))
        assert doc["record_count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# FreshnessCheckTool
# ══════════════════════════════════════════════════════════════════════════════

class TestFreshnessCheckTool:

    @pytest.fixture
    def report_with_sources(self) -> FreshnessReport:
        from datetime import UTC, datetime
        from isa_cad.core.models.freshness import DataSourceFreshness
        fresh = DataSourceFreshness(
            source_type=DataSourceType.CLOUD_INVENTORY,
            collected_at=datetime.now(UTC),
            freshness_score=0.95,
            age_hours=2.5,
            is_stale=False,
            label="2h",
        )
        stale = DataSourceFreshness(
            source_type=DataSourceType.PRICING_DATA,
            collected_at=datetime.now(UTC),
            freshness_score=0.10,
            age_hours=200.0,
            is_stale=True,
            label="8d",
        )
        report = FreshnessReport(sources=[fresh, stale])
        return report

    @pytest.fixture
    def tool(self, report_with_sources) -> FreshnessCheckTool:
        return FreshnessCheckTool(freshness_report=report_with_sources)

    @pytest.fixture
    def empty_tool(self) -> FreshnessCheckTool:
        return FreshnessCheckTool(freshness_report=FreshnessReport())

    def test_name(self, tool):
        assert tool.name == "freshness_check"

    def test_returns_valid_json(self, tool):
        result = tool._run("cloud_inventory")
        assert isinstance(json.loads(result), dict)

    def test_fresh_source_not_stale(self, tool):
        doc = json.loads(tool._run("cloud_inventory"))
        assert doc["is_stale"] is False
        assert doc["age_hours"] == pytest.approx(2.5, abs=0.01)

    def test_stale_source_is_stale(self, tool):
        doc = json.loads(tool._run("pricing_data"))
        assert doc["is_stale"] is True

    def test_stale_age_hours(self, tool):
        doc = json.loads(tool._run("pricing_data"))
        assert doc["age_hours"] == pytest.approx(200.0, abs=0.01)

    def test_stale_label(self, tool):
        doc = json.loads(tool._run("pricing_data"))
        assert doc["label"] == "8d"

    def test_missing_source_returns_stale(self, tool):
        doc = json.loads(tool._run("runtime_metrics"))
        assert doc["is_stale"] is True
        assert "note" in doc

    def test_empty_report_missing_source(self, empty_tool):
        doc = json.loads(empty_tool._run("cloud_inventory"))
        assert doc["is_stale"] is True
