from __future__ import annotations

"""
tests/unit/test_llm_reviewers.py
==================================
Unit tests for the LLM-backed reviewer layer.

All tests mock the LLM to avoid real API calls.  We verify:
  - Correct JSON parsing into the right reviewer output model
  - Fallback behaviour when LLM raises an exception
  - Fallback behaviour when LLM returns unparseable content
  - AgentState key written correctly for each reviewer type
  - LLMParallelReviewerNode aggregation
  - Settings-driven provider selection (import smoke test)
  - build_llm_graph() compiles without API keys
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.reviewers.llm import (
    LLMCostReviewer,
    LLMParallelReviewerNode,
    LLMPerformanceReviewer,
    LLMSecurityReviewer,
)
from isa_cad.core.models.enums import ReviewerStatus, ReviewerType


# ── Mock LLM factory ──────────────────────────────────────────────────────────

def _mock_llm(response_json: dict[str, Any] | None = None, raises: Exception | None = None):
    """
    Create a mock BaseChatModel that returns a pre-defined JSON response.

    If ``raises`` is provided, the mock's invoke() raises that exception.
    If ``response_json`` is None, returns an unparseable string response.
    """
    llm = MagicMock()
    bound = MagicMock()
    llm.bind_tools.return_value = bound

    if raises is not None:
        bound.invoke.side_effect = raises
    elif response_json is None:
        msg = MagicMock()
        msg.content = "I cannot provide a structured response."
        bound.invoke.return_value = msg
    else:
        msg = MagicMock()
        msg.content = json.dumps(response_json)
        bound.invoke.return_value = msg

    return llm


def _base_state() -> AgentState:
    from isa_cad.state.canvas_state import ComponentGraph
    return {
        "session_id":          "s-llm-test",
        "source_component_id": "api",
        "baseline_ref":        "arch.prod",
        "resolved_graph":      ComponentGraph(),
        "design_delta":        {"added": [], "removed": [], "modified": ["api"]},
    }


# ── Cost response fixtures ─────────────────────────────────────────────────────

def _cost_pass_response() -> dict[str, Any]:
    return {
        "status":        "pass",
        "score":         0.85,
        "confidence":    0.90,
        "tco_delta_usd": 50.0,
        "recommendation": "Cost increase is within budget.",
        "findings":      [],
        "assumptions":   ["Baseline uses t3.medium instances."],
        "missing_inputs": [],
    }


def _cost_fail_response() -> dict[str, Any]:
    return {
        "status":        "fail",
        "score":         0.20,
        "confidence":    0.85,
        "tco_delta_usd": 3500.0,
        "recommendation": "Unacceptable cost increase — $3500/month over baseline.",
        "findings": [
            {"severity": "critical", "title": "Cost spike", "description": "New DB tier too expensive."}
        ],
        "assumptions":   [],
        "missing_inputs": [],
    }


# ── Performance response fixtures ─────────────────────────────────────────────

def _perf_pass_response() -> dict[str, Any]:
    return {
        "status":          "pass",
        "score":           0.80,
        "confidence":      0.88,
        "latency_delta":   "+5ms p95",
        "bottleneck_risk": "low",
        "recommendation":  "Latency within SLO.",
        "findings":        [],
        "assumptions":     [],
        "missing_inputs":  [],
    }


def _perf_warn_response() -> dict[str, Any]:
    return {
        "status":          "warning",
        "score":           0.55,
        "confidence":      0.70,
        "latency_delta":   "+45ms p95",
        "bottleneck_risk": "high",
        "recommendation":  "New DB query on critical path degrades SLO.",
        "findings": [
            {"severity": "high", "title": "Bottleneck risk",
             "description": "Direct DB call from gateway."}
        ],
        "assumptions":     [],
        "missing_inputs":  [],
    }


# ── Security response fixtures ────────────────────────────────────────────────

def _sec_pass_response() -> dict[str, Any]:
    return {
        "status":                    "pass",
        "score":                     0.90,
        "confidence":                0.92,
        "trust_boundary_violations": [],
        "pii_flow_status":           "pass",
        "compliance_status":         "pass",
        "public_exposure_risk":      "low",
        "iam_scope_risk":            "low",
        "recommendation":            "No security concerns.",
        "findings":                  [],
        "assumptions":               [],
        "missing_inputs":            [],
    }


def _sec_fail_response() -> dict[str, Any]:
    return {
        "status":                    "fail",
        "score":                     0.10,
        "confidence":                0.95,
        "trust_boundary_violations": ["gateway → db without auth layer"],
        "pii_flow_status":           "fail",
        "compliance_status":         "fail",
        "public_exposure_risk":      "high",
        "iam_scope_risk":            "high",
        "recommendation":            "Critical trust boundary violation.",
        "findings": [
            {"severity": "critical", "title": "PII exposed",
             "description": "DB accessible from gateway directly."}
        ],
        "assumptions":   [],
        "missing_inputs": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# LLMCostReviewer
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMCostReviewer:

    def test_reviewer_type(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        assert r.reviewer_type == ReviewerType.COST

    def test_returns_cost_review_key(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        result = r(_base_state())
        assert "cost_review" in result

    def test_pass_status_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        out = r(_base_state())["cost_review"]
        assert out.status == ReviewerStatus.PASS

    def test_score_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        out = r(_base_state())["cost_review"]
        assert out.score == pytest.approx(0.85)

    def test_confidence_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        out = r(_base_state())["cost_review"]
        assert out.confidence == pytest.approx(0.90)

    def test_tco_delta_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        out = r(_base_state())["cost_review"]
        assert out.tco_delta_usd == pytest.approx(50.0)

    def test_fail_status_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_fail_response()))
        out = r(_base_state())["cost_review"]
        assert out.status == ReviewerStatus.FAIL

    def test_findings_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_fail_response()))
        out = r(_base_state())["cost_review"]
        assert len(out.findings) == 1
        assert out.findings[0].severity == "critical"

    def test_assumptions_parsed(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        out = r(_base_state())["cost_review"]
        assert out.assumptions == ["Baseline uses t3.medium instances."]

    def test_fallback_on_llm_exception(self):
        r = LLMCostReviewer(llm=_mock_llm(raises=RuntimeError("API down")))
        out = r(_base_state())["cost_review"]
        assert out.status == ReviewerStatus.UNKNOWN
        assert out.confidence == pytest.approx(0.0)
        assert "LLM reviewer unavailable" in out.recommendation

    def test_fallback_on_unparseable_response(self):
        r = LLMCostReviewer(llm=_mock_llm(response_json=None))
        out = r(_base_state())["cost_review"]
        assert out.status == ReviewerStatus.UNKNOWN

    def test_state_passthrough(self):
        r = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        state = {**_base_state(), "session_id": "preserved"}
        result = r(state)
        assert result["session_id"] == "preserved"


# ══════════════════════════════════════════════════════════════════════════════
# LLMPerformanceReviewer
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMPerformanceReviewer:

    def test_reviewer_type(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        assert r.reviewer_type == ReviewerType.PERFORMANCE

    def test_returns_performance_review_key(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        result = r(_base_state())
        assert "performance_review" in result

    def test_pass_status(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        out = r(_base_state())["performance_review"]
        assert out.status == ReviewerStatus.PASS

    def test_latency_delta_parsed(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        out = r(_base_state())["performance_review"]
        assert out.latency_delta == "+5ms p95"

    def test_bottleneck_risk_parsed(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        out = r(_base_state())["performance_review"]
        assert out.bottleneck_risk == "low"

    def test_warning_status(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_warn_response()))
        out = r(_base_state())["performance_review"]
        assert out.status == ReviewerStatus.WARNING

    def test_high_bottleneck_risk(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(_perf_warn_response()))
        out = r(_base_state())["performance_review"]
        assert out.bottleneck_risk == "high"

    def test_fallback_on_exception(self):
        r = LLMPerformanceReviewer(llm=_mock_llm(raises=ConnectionError("timeout")))
        out = r(_base_state())["performance_review"]
        assert out.status == ReviewerStatus.UNKNOWN


# ══════════════════════════════════════════════════════════════════════════════
# LLMSecurityReviewer
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMSecurityReviewer:

    def test_reviewer_type(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        assert r.reviewer_type == ReviewerType.SECURITY

    def test_returns_security_review_key(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        result = r(_base_state())
        assert "security_review" in result

    def test_pass_status(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        out = r(_base_state())["security_review"]
        assert out.status == ReviewerStatus.PASS

    def test_no_violations_on_pass(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        out = r(_base_state())["security_review"]
        assert out.trust_boundary_violations == []

    def test_pii_pass(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        out = r(_base_state())["security_review"]
        assert out.pii_flow_status == "pass"

    def test_fail_status_with_violations(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_fail_response()))
        out = r(_base_state())["security_review"]
        assert out.status == ReviewerStatus.FAIL
        assert len(out.trust_boundary_violations) == 1

    def test_pii_fail(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_fail_response()))
        out = r(_base_state())["security_review"]
        assert out.pii_flow_status == "fail"

    def test_iam_risk_parsed(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_fail_response()))
        out = r(_base_state())["security_review"]
        assert out.iam_scope_risk == "high"

    def test_public_exposure_parsed(self):
        r = LLMSecurityReviewer(llm=_mock_llm(_sec_fail_response()))
        out = r(_base_state())["security_review"]
        assert out.public_exposure_risk == "high"

    def test_fallback_on_exception(self):
        r = LLMSecurityReviewer(llm=_mock_llm(raises=ValueError("bad")))
        out = r(_base_state())["security_review"]
        assert out.status == ReviewerStatus.UNKNOWN
        assert out.pii_flow_status == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# LLMParallelReviewerNode
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMParallelReviewerNode:

    def _make_node(self) -> LLMParallelReviewerNode:
        """Build an orchestrator with three separate mocked LLMs."""
        node = LLMParallelReviewerNode.__new__(LLMParallelReviewerNode)
        node._cost = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        node._perf = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        node._sec  = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        node._max_workers = 3
        return node

    def test_all_keys_present(self):
        node = self._make_node()
        result = node(_base_state())
        for key in ("cost_review", "performance_review", "security_review",
                    "reviewer_summary", "is_blocked", "block_reasons"):
            assert key in result, f"missing key: {key}"

    def test_not_blocked_when_all_pass(self):
        node = self._make_node()
        result = node(_base_state())
        assert result["is_blocked"] is False

    def test_blocked_when_security_fails(self):
        node = LLMParallelReviewerNode.__new__(LLMParallelReviewerNode)
        node._cost = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        node._perf = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        node._sec  = LLMSecurityReviewer(llm=_mock_llm(_sec_fail_response()))
        node._max_workers = 3

        result = node(_base_state())
        assert result["is_blocked"] is True

    def test_block_reasons_populated_on_fail(self):
        node = LLMParallelReviewerNode.__new__(LLMParallelReviewerNode)
        node._cost = LLMCostReviewer(llm=_mock_llm(_cost_fail_response()))
        node._perf = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        node._sec  = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        node._max_workers = 3

        result = node(_base_state())
        assert result["block_reasons"]

    def test_reviewer_summary_has_overall_status(self):
        node = self._make_node()
        result = node(_base_state())
        assert "overall_status" in result["reviewer_summary"]

    def test_state_passthrough(self):
        node = self._make_node()
        state = {**_base_state(), "session_id": "llm-session"}
        result = node(state)
        assert result["session_id"] == "llm-session"


# ══════════════════════════════════════════════════════════════════════════════
# build_llm_graph() smoke tests (no API calls)
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildLlmGraph:

    def test_compiles(self):
        from isa_cad.agent import build_llm_graph
        # Use a stub reviewer so no API call is made
        from tests.integration.test_graph_e2e import _ContextStub, _DeltaStub
        node = LLMParallelReviewerNode.__new__(LLMParallelReviewerNode)
        node._cost = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        node._perf = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        node._sec  = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        node._max_workers = 3

        g = build_llm_graph(parallel_reviewer_node=node)
        assert hasattr(g, "invoke")

    def test_node_count_same_as_base_graph(self):
        from isa_cad.agent import build_graph, build_llm_graph
        node = LLMParallelReviewerNode.__new__(LLMParallelReviewerNode)
        node._cost = LLMCostReviewer(llm=_mock_llm(_cost_pass_response()))
        node._perf = LLMPerformanceReviewer(llm=_mock_llm(_perf_pass_response()))
        node._sec  = LLMSecurityReviewer(llm=_mock_llm(_sec_pass_response()))
        node._max_workers = 3

        g_base = build_graph()
        g_llm  = build_llm_graph(parallel_reviewer_node=node)
        assert len(list(g_llm.nodes)) == len(list(g_base.nodes))


# ══════════════════════════════════════════════════════════════════════════════
# JSON extraction helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestJsonExtraction:
    """Test the _extract_json method in isolation."""

    def _reviewer(self) -> LLMCostReviewer:
        return LLMCostReviewer(llm=MagicMock())

    def test_dict_content(self):
        r = self._reviewer()
        msg = MagicMock()
        msg.content = {"status": "pass"}
        assert r._extract_json(msg) == {"status": "pass"}

    def test_plain_json_string(self):
        r = self._reviewer()
        msg = MagicMock()
        msg.content = '{"status": "pass", "score": 0.9}'
        result = r._extract_json(msg)
        assert result["status"] == "pass"

    def test_fenced_code_block(self):
        r = self._reviewer()
        msg = MagicMock()
        msg.content = 'Some preamble\n```json\n{"status": "pass"}\n```'
        result = r._extract_json(msg)
        assert result["status"] == "pass"

    def test_plain_string_no_json_returns_none(self):
        r = self._reviewer()
        msg = MagicMock()
        msg.content = "I cannot answer this question."
        assert r._extract_json(msg) is None

    def test_none_content_returns_none(self):
        r = self._reviewer()
        msg = MagicMock()
        msg.content = None
        assert r._extract_json(msg) is None
