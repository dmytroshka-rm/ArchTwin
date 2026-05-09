from __future__ import annotations

"""
isa_cad/output/formatters/base.py
==================================
Base protocol and shared helpers for all output formatters.

Every formatter receives the full ``AgentState`` (as a plain dict) and
produces a ``FormattedOutput`` dataclass with the serialised result plus
metadata.  Formatters are pure functions — they never mutate state.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class FormattedOutput:
    """
    Container returned by every formatter.

    Attributes
    ----------
    content   The formatted string (Markdown text, JSON string, YAML string …)
    media_type  MIME type of the content (e.g. ``"text/markdown"``)
    metadata    Optional dict of extra metadata (proposal_id, decision, …)
    """
    content:    str
    media_type: str
    metadata:   dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class OutputFormatter(Protocol):
    """
    Protocol satisfied by all concrete formatter classes.

    Implementors must define ``format(state)`` and expose ``media_type``.
    """
    media_type: str

    def format(self, state: dict[str, Any]) -> FormattedOutput:
        ...


# ── Shared extraction helpers ─────────────────────────────────────────────────

def _fo(state: dict[str, Any]) -> dict[str, Any]:
    """Return final_output sub-dict (never None)."""
    return state.get("final_output") or {}


def _decision_badge(decision: str) -> str:
    """Map ProposalStatus value to an emoji badge string."""
    return {
        "approved":             "[APPROVED]",
        "blocked":              "[BLOCKED]",
        "candidate_for_review": "[NEEDS REVIEW]",
        "sandbox_layer":        "[SANDBOX]",
        "rejected":             "[REJECTED]",
    }.get(decision, f"[{decision.upper()}]")


def _score_bar(score: float, width: int = 20) -> str:
    """ASCII progress bar for a 0–1 score."""
    filled = round(score * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {score:.2f}"


def _fmt_bool(v: Any) -> str:
    return "yes" if v else "no"
