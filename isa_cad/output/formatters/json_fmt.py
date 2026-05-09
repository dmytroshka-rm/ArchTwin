from __future__ import annotations

"""
isa_cad/output/formatters/json_fmt.py
=======================================
JSON formatter — serialises the Decision-Grade Output Contract to
a clean, self-contained JSON document.

The JSON document includes:
    - ``final_output``     core contract fields
    - ``recommendations``  goal-aligned suggestions (from state)
    - ``human_review``     escalation request (from state, when required)
    - ``required_actions`` persona action lists (from final_output)
    - ``isa_yaml_patch``   schema patch (from state, when present)
    - ``meta``             formatter metadata
"""

import json
from typing import Any

from .base import FormattedOutput, _fo


class JsonFormatter:
    """Formats the pipeline AgentState as a JSON document."""

    media_type = "application/json"

    def __init__(self, indent: int = 2, ensure_ascii: bool = False) -> None:
        self._indent = indent
        self._ensure_ascii = ensure_ascii

    def format(self, state: dict[str, Any]) -> FormattedOutput:  # noqa: A003
        fo = _fo(state)
        doc = self._build_doc(fo, state)

        content = json.dumps(doc, indent=self._indent,
                             ensure_ascii=self._ensure_ascii, default=str)

        return FormattedOutput(
            content=content,
            media_type=self.media_type,
            metadata={
                "proposal_id": fo.get("proposal_id"),
                "decision":    fo.get("decision"),
                "score":       fo.get("recommendation_score"),
            },
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _build_doc(
        self, fo: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "final_output": {
                "proposal_id":           fo.get("proposal_id"),
                "decision":              fo.get("decision"),
                "recommendation_score":  fo.get("recommendation_score"),
                "output_mode":           fo.get("output_mode"),
                "is_blocked":            fo.get("is_blocked", False),
                "block_reasons":         fo.get("block_reasons") or [],
                "veto_product":          fo.get("veto_product"),
                "reviewer_signals":      fo.get("reviewer_signals") or {},
                "blast_radius_summary":  fo.get("blast_radius_summary", ""),
                "high_risk_components":  fo.get("high_risk_components", 0),
                "total_blast_impact":    fo.get("total_blast_impact", 0.0),
                "calibration_summary":   fo.get("calibration_summary", ""),
                "human_review_required": fo.get("human_review_required", False),
                "safety_buffer_applied": fo.get("safety_buffer_applied", False),
            },
        }

        # Optional enrichments from later nodes
        if fo.get("required_actions") is not None:
            doc["final_output"]["required_actions"] = fo["required_actions"]
        if fo.get("isa_yaml_valid") is not None:
            doc["final_output"]["isa_yaml_valid"] = fo["isa_yaml_valid"]
        if fo.get("adr_required"):
            doc["final_output"]["adr_required"] = fo["adr_required"]
        if fo.get("needs_rerun"):
            doc["final_output"]["needs_rerun"] = fo["needs_rerun"]
            doc["final_output"]["rerun_reason"] = fo.get("rerun_reason", "")

        # Recommendations (lives in state, not final_output)
        recs = state.get("recommendations")
        if recs:
            doc["recommendations"] = recs

        # Human review request (lives in state)
        hrr = state.get("human_review_request")
        if hrr and hrr.get("required"):
            doc["human_review"] = hrr

        # ISA YAML patch (lives in state)
        patch = state.get("isa_yaml_patch")
        if patch:
            doc["isa_yaml_patch"] = patch

        doc["meta"] = {
            "formatter": "JsonFormatter",
            "isa_cad_version": "0.5.3",
        }

        return doc
