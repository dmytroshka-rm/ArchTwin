from __future__ import annotations

"""
isa_cad/output/formatters/markdown.py
=======================================
Markdown formatter — produces a human-readable architecture review report
from the pipeline's final AgentState.

Output sections
---------------
1. Header — proposal ID, decision badge, output mode
2. Score — recommendation score bar + veto product
3. Reviewer Signals — per-reviewer scores and overall status
4. Blast Radius — summary + high-risk count
5. Block Reasons — only when is_blocked=True
6. Required Actions — per-persona action lists
7. Recommendations — top-N goal-aligned suggestions
8. Calibration — summary + safety buffer flag
9. Human Review — escalation level + reasons + options (when required)
10. ISA YAML — validation status
11. Footer — output mode caveat
"""

from typing import Any

from .base import FormattedOutput, _decision_badge, _fo, _fmt_bool, _score_bar


class MarkdownFormatter:
    """Formats the full pipeline AgentState as a Markdown report."""

    media_type = "text/markdown"

    def format(self, state: dict[str, Any]) -> FormattedOutput:  # noqa: A003
        fo = _fo(state)
        lines: list[str] = []

        self._header(lines, fo)
        self._score_section(lines, fo)
        self._reviewer_section(lines, fo)
        self._blast_section(lines, fo)
        self._block_section(lines, fo)
        self._required_actions_section(lines, fo)
        self._recommendations_section(lines, state)
        self._calibration_section(lines, fo)
        self._human_review_section(lines, state)
        self._isa_yaml_section(lines, fo)
        self._footer(lines, fo)

        content = "\n".join(lines)
        return FormattedOutput(
            content=content,
            media_type=self.media_type,
            metadata={
                "proposal_id": fo.get("proposal_id"),
                "decision":    fo.get("decision"),
                "score":       fo.get("recommendation_score"),
            },
        )

    # ── sections ─────────────────────────────────────────────────────────────

    def _header(self, lines: list[str], fo: dict[str, Any]) -> None:
        proposal_id = fo.get("proposal_id") or "unknown"
        decision    = fo.get("decision", "unknown")
        output_mode = fo.get("output_mode", "exploratory_estimate")
        badge       = _decision_badge(decision)

        lines += [
            f"# ISA-CAD Architecture Review Report",
            f"",
            f"**Proposal:** `{proposal_id}`  ",
            f"**Decision:** {badge}  ",
            f"**Output Mode:** `{output_mode}`",
            f"",
            "---",
            "",
        ]

    def _score_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        score        = fo.get("recommendation_score", 0.0)
        veto_product = fo.get("veto_product", 0.0)

        lines += [
            "## Score",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Recommendation Score | `{score:.4f}` |",
            f"| Veto Gate Product    | `{veto_product:.4f}` |",
            f"",
            f"**Score:** {_score_bar(score)}",
            "",
        ]

    def _reviewer_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        signals = fo.get("reviewer_signals") or {}
        overall = signals.get("overall_status", "unknown")

        cost  = signals.get("cost_score")
        perf  = signals.get("performance_score")
        sec   = signals.get("security_score")

        def _fmt(v: float | None) -> str:
            return f"{v:.4f}" if v is not None else "—"

        lines += [
            "## Reviewer Signals",
            "",
            f"| Reviewer    | Score   |",
            f"|-------------|---------|",
            f"| Cost        | `{_fmt(cost)}` |",
            f"| Performance | `{_fmt(perf)}` |",
            f"| Security    | `{_fmt(sec)}` |",
            f"",
            f"**Overall status:** `{overall}`",
            "",
        ]

    def _blast_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        summary      = fo.get("blast_radius_summary", "")
        high_risk    = fo.get("high_risk_components", 0)
        total_impact = fo.get("total_blast_impact", 0.0)

        lines += [
            "## Blast Radius",
            "",
            f"- **High-risk Tier-1 components:** {high_risk}",
            f"- **Total impact score:** {total_impact:.2f}",
        ]
        if summary:
            lines.append(f"- **Summary:** {summary}")
        lines.append("")

    def _block_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        if not fo.get("is_blocked"):
            return
        reasons: list[str] = fo.get("block_reasons") or []
        lines += ["## Block Reasons", ""]
        for r in reasons:
            lines.append(f"- {r}")
        lines.append("")

    def _required_actions_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        ra: dict[str, Any] = fo.get("required_actions") or {}
        if not ra:
            return

        personas = [
            ("developer",     "Developer"),
            ("architect",     "Architect"),
            ("security_ops",  "Security Ops"),
            ("data_fidelity", "Data Fidelity"),
        ]

        has_any = any(ra.get(k) for k, _ in personas)
        if not has_any:
            return

        lines += ["## Required Actions", ""]
        for key, label in personas:
            actions: list[str] = ra.get(key) or []
            if actions:
                lines.append(f"### {label}")
                for a in actions:
                    lines.append(f"- {a}")
                lines.append("")

    def _recommendations_section(
        self, lines: list[str], state: dict[str, Any]
    ) -> None:
        recs: list[dict[str, Any]] = state.get("recommendations") or []
        if not recs:
            return

        lines += ["## Recommendations", ""]
        for rec in recs:
            score     = rec.get("goal_alignment", 0.0)
            title     = rec.get("title", "?")
            rationale = rec.get("rationale", "")
            changes   = rec.get("suggested_changes") or []
            expected  = rec.get("expected_improvements") or {}

            lines.append(f"### {title} *(alignment: {score:.2f})*")
            if rationale:
                lines.append(f"> {rationale}")
                lines.append("")
            if changes:
                lines.append("**Suggested changes:**")
                for c in changes:
                    lines.append(f"- {c}")
            if expected:
                lines.append("")
                lines.append("**Expected improvements:**")
                for metric, value in expected.items():
                    lines.append(f"- {metric}: {value}")
            lines.append("")

    def _calibration_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        summary = fo.get("calibration_summary", "")
        buffer  = fo.get("safety_buffer_applied", False)

        lines += [
            "## Calibration",
            "",
            f"- **Safety buffer applied:** {_fmt_bool(buffer)}",
        ]
        if summary:
            lines.append(f"- **Summary:** {summary}")
        lines.append("")

    def _human_review_section(
        self, lines: list[str], state: dict[str, Any]
    ) -> None:
        hrr: dict[str, Any] = state.get("human_review_request") or {}
        if not hrr.get("required"):
            return

        level   = hrr.get("escalation_level", "info").upper()
        reasons = hrr.get("reasons") or []
        options = hrr.get("options") or []
        hint    = hrr.get("deadline_hint", "")

        lines += [
            f"## Human Review Required — {level}",
            "",
        ]
        for r in reasons:
            lines.append(f"- {r}")
        if hint:
            lines += ["", f"> **Deadline hint:** {hint}"]
        if options:
            lines += ["", f"**Available decisions:** {', '.join(f'`{o}`' for o in options)}"]
        lines.append("")

    def _isa_yaml_section(self, lines: list[str], fo: dict[str, Any]) -> None:
        valid = fo.get("isa_yaml_valid")
        if valid is None:
            return
        status = "valid" if valid else "INVALID"
        lines += [
            "## ISA YAML Patch",
            "",
            f"- **Validation:** `{status}`",
            "",
        ]

    def _footer(self, lines: list[str], fo: dict[str, Any]) -> None:
        output_mode = fo.get("output_mode", "exploratory_estimate")
        caveat = (
            "_This report is a **Final Forecast** — data freshness confirmed._"
            if output_mode == "final_forecast"
            else (
                "_This report is an **Exploratory Estimate** — "
                "fidelity gate did not pass. Refresh the observed graph "
                "before treating this as a production decision._"
            )
        )
        lines += [
            "---",
            "",
            caveat,
            "",
            "*Generated by ISA-CAD v0.5.3*",
        ]
