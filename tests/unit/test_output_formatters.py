from __future__ import annotations

"""
tests/unit/test_output_formatters.py
=====================================
Unit tests for MarkdownFormatter, JsonFormatter, YamlFormatter,
and the FormattedOutput / OutputFormatter contracts.
"""

import json
from typing import Any

import pytest
import yaml

from isa_cad.output import (
    FormattedOutput,
    JsonFormatter,
    MarkdownFormatter,
    OutputFormatter,
    YamlFormatter,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _approved_state() -> dict[str, Any]:
    return {
        "final_output": {
            "proposal_id":           "p-fmt-01",
            "decision":              "approved",
            "recommendation_score":  0.82,
            "output_mode":           "final_forecast",
            "is_blocked":            False,
            "block_reasons":         [],
            "veto_product":          1.0,
            "reviewer_signals": {
                "cost_score":        0.80,
                "performance_score": 0.85,
                "security_score":    0.90,
                "overall_status":    "pass",
            },
            "blast_radius_summary":  "no high-risk components",
            "high_risk_components":  0,
            "total_blast_impact":    0.0,
            "calibration_summary":   "no bias detected",
            "human_review_required": False,
            "safety_buffer_applied": False,
            "required_actions": {
                "developer":     [],
                "architect":     [],
                "security_ops":  [],
                "data_fidelity": [],
            },
            "isa_yaml_valid": True,
        },
        "recommendations": [
            {
                "id":               "rec-001",
                "title":            "Add Redis caching layer",
                "rationale":        "Reduce DB load on Tier-1 components.",
                "goal_alignment":   0.75,
                "suggested_changes": ["Add Redis between API and DB"],
                "expected_improvements": {"latency": "-30%"},
            }
        ],
        "human_review_request": {"required": False},
        "isa_yaml_patch": {"design_proposals": []},
    }


def _blocked_state() -> dict[str, Any]:
    return {
        "final_output": {
            "proposal_id":           "p-fmt-02",
            "decision":              "blocked",
            "recommendation_score":  0.15,
            "output_mode":           "exploratory_estimate",
            "is_blocked":            True,
            "block_reasons":         [
                "[security_gate] Trust boundary violation.",
                "[human_decision] Blocked by reviewer.",
            ],
            "veto_product":          0.0,
            "reviewer_signals": {
                "cost_score":        0.70,
                "performance_score": 0.65,
                "security_score":    0.10,
                "overall_status":    "fail",
            },
            "blast_radius_summary":  "3 high-risk components affected",
            "high_risk_components":  3,
            "total_blast_impact":    6.0,
            "calibration_summary":   "safety buffer applied",
            "human_review_required": True,
            "safety_buffer_applied": True,
        },
        "recommendations": [],
        "human_review_request": {
            "required":          True,
            "escalation_level":  "critical",
            "reasons":           ["Proposal is BLOCKED. Review block reasons."],
            "options":           ["approve_sandbox_layer", "block_proposal", "modify_goal"],
            "deadline_hint":     "",
        },
    }


def _candidate_state() -> dict[str, Any]:
    return {
        "final_output": {
            "proposal_id":           "p-fmt-03",
            "decision":              "candidate_for_review",
            "recommendation_score":  0.55,
            "output_mode":           "exploratory_estimate",
            "is_blocked":            False,
            "block_reasons":         [],
            "veto_product":          0.5,
            "reviewer_signals": {
                "cost_score":        0.55,
                "performance_score": 0.60,
                "security_score":    0.75,
                "overall_status":    "warning",
            },
            "blast_radius_summary":  "",
            "high_risk_components":  0,
            "total_blast_impact":    0.0,
            "calibration_summary":   "",
            "human_review_required": False,
            "safety_buffer_applied": False,
        },
        "recommendations": [],
        "human_review_request": {
            "required":          True,
            "escalation_level":  "warning",
            "reasons":           ["Score below threshold."],
            "options":           ["accept_risk_with_adr", "approve_sandbox_layer"],
            "deadline_hint":     "Refresh before final forecast.",
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# FormattedOutput dataclass
# ══════════════════════════════════════════════════════════════════════════════

class TestFormattedOutput:

    def test_frozen(self):
        fo = FormattedOutput(content="x", media_type="text/plain")
        with pytest.raises((TypeError, AttributeError)):
            fo.content = "y"  # type: ignore[misc]

    def test_default_metadata_empty(self):
        fo = FormattedOutput(content="", media_type="text/plain")
        assert fo.metadata == {}

    def test_metadata_stored(self):
        fo = FormattedOutput(content="", media_type="text/plain",
                             metadata={"k": "v"})
        assert fo.metadata["k"] == "v"


# ══════════════════════════════════════════════════════════════════════════════
# OutputFormatter protocol
# ══════════════════════════════════════════════════════════════════════════════

class TestOutputFormatterProtocol:

    def test_markdown_satisfies_protocol(self):
        assert isinstance(MarkdownFormatter(), OutputFormatter)

    def test_json_satisfies_protocol(self):
        assert isinstance(JsonFormatter(), OutputFormatter)

    def test_yaml_satisfies_protocol(self):
        assert isinstance(YamlFormatter(), OutputFormatter)


# ══════════════════════════════════════════════════════════════════════════════
# MarkdownFormatter
# ══════════════════════════════════════════════════════════════════════════════

class TestMarkdownFormatter:
    fmt = MarkdownFormatter()

    # ── Contract ──────────────────────────────────────────────────────────────

    def test_returns_formatted_output(self):
        r = self.fmt.format(_approved_state())
        assert isinstance(r, FormattedOutput)

    def test_media_type(self):
        assert self.fmt.media_type == "text/markdown"
        r = self.fmt.format(_approved_state())
        assert r.media_type == "text/markdown"

    def test_metadata_contains_decision(self):
        r = self.fmt.format(_approved_state())
        assert r.metadata["decision"] == "approved"
        assert r.metadata["proposal_id"] == "p-fmt-01"
        assert r.metadata["score"] == 0.82

    # ── Content — approved ────────────────────────────────────────────────────

    def test_header_contains_proposal_id(self):
        r = self.fmt.format(_approved_state())
        assert "p-fmt-01" in r.content

    def test_header_contains_approved_badge(self):
        r = self.fmt.format(_approved_state())
        assert "[APPROVED]" in r.content

    def test_score_present(self):
        r = self.fmt.format(_approved_state())
        assert "0.8200" in r.content

    def test_reviewer_scores_present(self):
        r = self.fmt.format(_approved_state())
        assert "0.8000" in r.content   # cost
        assert "0.8500" in r.content   # perf
        assert "0.9000" in r.content   # sec

    def test_final_forecast_footer(self):
        r = self.fmt.format(_approved_state())
        assert "Final Forecast" in r.content

    def test_recommendation_in_output(self):
        r = self.fmt.format(_approved_state())
        assert "Redis" in r.content
        assert "0.75" in r.content

    def test_isa_yaml_valid_shown(self):
        r = self.fmt.format(_approved_state())
        assert "valid" in r.content

    # ── Content — blocked ─────────────────────────────────────────────────────

    def test_blocked_badge(self):
        r = self.fmt.format(_blocked_state())
        assert "[BLOCKED]" in r.content

    def test_block_reasons_shown(self):
        r = self.fmt.format(_blocked_state())
        assert "Trust boundary violation" in r.content

    def test_human_review_critical_shown(self):
        r = self.fmt.format(_blocked_state())
        assert "CRITICAL" in r.content

    def test_exploratory_estimate_footer_blocked(self):
        r = self.fmt.format(_blocked_state())
        assert "Exploratory Estimate" in r.content

    # ── Content — candidate ───────────────────────────────────────────────────

    def test_candidate_badge(self):
        r = self.fmt.format(_candidate_state())
        assert "[NEEDS REVIEW]" in r.content

    def test_human_review_warning_shown(self):
        r = self.fmt.format(_candidate_state())
        assert "WARNING" in r.content

    def test_deadline_hint_shown(self):
        r = self.fmt.format(_candidate_state())
        assert "Refresh before final forecast" in r.content

    # ── Empty state gracefully handled ────────────────────────────────────────

    def test_empty_state_no_crash(self):
        r = self.fmt.format({})
        assert isinstance(r.content, str)
        assert len(r.content) > 0


# ══════════════════════════════════════════════════════════════════════════════
# JsonFormatter
# ══════════════════════════════════════════════════════════════════════════════

class TestJsonFormatter:
    fmt = JsonFormatter()

    def test_returns_formatted_output(self):
        r = self.fmt.format(_approved_state())
        assert isinstance(r, FormattedOutput)

    def test_media_type(self):
        assert self.fmt.media_type == "application/json"
        r = self.fmt.format(_approved_state())
        assert r.media_type == "application/json"

    def test_content_is_valid_json(self):
        r = self.fmt.format(_approved_state())
        doc = json.loads(r.content)
        assert isinstance(doc, dict)

    def test_final_output_key_present(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert "final_output" in doc

    def test_decision_correct(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert doc["final_output"]["decision"] == "approved"

    def test_score_correct(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert doc["final_output"]["recommendation_score"] == 0.82

    def test_recommendations_included(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert "recommendations" in doc
        assert len(doc["recommendations"]) == 1

    def test_human_review_not_included_when_not_required(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert "human_review" not in doc

    def test_human_review_included_when_required(self):
        doc = json.loads(self.fmt.format(_blocked_state()).content)
        assert "human_review" in doc
        assert doc["human_review"]["escalation_level"] == "critical"

    def test_isa_yaml_patch_included(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert "isa_yaml_patch" in doc

    def test_meta_version(self):
        doc = json.loads(self.fmt.format(_approved_state()).content)
        assert doc["meta"]["isa_cad_version"] == "0.5.3"

    def test_custom_indent(self):
        fmt4 = JsonFormatter(indent=4)
        r = fmt4.format(_approved_state())
        # 4-space indent means first key starts with 4 spaces
        assert '    "final_output"' in r.content

    def test_empty_state_no_crash(self):
        r = self.fmt.format({})
        doc = json.loads(r.content)
        assert "final_output" in doc

    def test_blocked_block_reasons_in_output(self):
        doc = json.loads(self.fmt.format(_blocked_state()).content)
        reasons = doc["final_output"]["block_reasons"]
        assert any("Trust boundary" in r for r in reasons)

    def test_adr_required_included_when_present(self):
        state = _approved_state()
        state["final_output"]["adr_required"] = True
        doc = json.loads(self.fmt.format(state).content)
        assert doc["final_output"]["adr_required"] is True

    def test_needs_rerun_included_when_present(self):
        state = _approved_state()
        state["final_output"]["needs_rerun"] = True
        state["final_output"]["rerun_reason"] = "goal changed"
        doc = json.loads(self.fmt.format(state).content)
        assert doc["final_output"]["needs_rerun"] is True
        assert doc["final_output"]["rerun_reason"] == "goal changed"


# ══════════════════════════════════════════════════════════════════════════════
# YamlFormatter
# ══════════════════════════════════════════════════════════════════════════════

class TestYamlFormatter:
    fmt = YamlFormatter()

    def test_returns_formatted_output(self):
        r = self.fmt.format(_approved_state())
        assert isinstance(r, FormattedOutput)

    def test_media_type(self):
        assert self.fmt.media_type == "application/yaml"
        r = self.fmt.format(_approved_state())
        assert r.media_type == "application/yaml"

    def test_content_is_valid_yaml(self):
        r = self.fmt.format(_approved_state())
        doc = yaml.safe_load(r.content)
        assert isinstance(doc, dict)

    def test_final_output_key_present(self):
        doc = yaml.safe_load(self.fmt.format(_approved_state()).content)
        assert "final_output" in doc

    def test_decision_correct(self):
        doc = yaml.safe_load(self.fmt.format(_approved_state()).content)
        assert doc["final_output"]["decision"] == "approved"

    def test_score_correct(self):
        doc = yaml.safe_load(self.fmt.format(_approved_state()).content)
        assert doc["final_output"]["recommendation_score"] == pytest.approx(0.82)

    def test_yaml_formatter_name_in_meta(self):
        doc = yaml.safe_load(self.fmt.format(_approved_state()).content)
        assert doc["meta"]["formatter"] == "YamlFormatter"

    def test_human_review_included_when_required(self):
        doc = yaml.safe_load(self.fmt.format(_blocked_state()).content)
        assert "human_review" in doc

    def test_empty_state_no_crash(self):
        r = self.fmt.format({})
        doc = yaml.safe_load(r.content)
        assert isinstance(doc, dict)

    def test_parity_with_json(self):
        """JSON and YAML formatters should produce structurally equivalent docs."""
        state = _approved_state()
        json_doc = json.loads(JsonFormatter().format(state).content)
        yaml_doc = yaml.safe_load(YamlFormatter().format(state).content)
        # Top-level keys must match (YAML meta has different formatter name)
        assert set(json_doc.keys()) == set(yaml_doc.keys())
        assert (json_doc["final_output"]["decision"] ==
                yaml_doc["final_output"]["decision"])
