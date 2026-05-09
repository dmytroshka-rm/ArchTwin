from __future__ import annotations

"""
isa_cad/agent/reviewers/llm/base.py
=====================================
Base class for all LLM-backed reviewers.

Handles:
  - LLM construction (Anthropic or OpenAI, from settings or explicit injection)
  - Tool binding (all five agent tools)
  - State → prompt context serialisation
  - Structured output parsing + fallback on parse error
  - Graceful degradation: if the LLM call fails, returns a DEGRADED output
    (same as the rule-based reviewer would produce with no inputs)

Provider selection (in priority order):
  1. Explicit ``llm`` argument passed to the constructor
  2. ``LLM_PROVIDER`` setting: "anthropic" → ChatAnthropic, "openai" → ChatOpenAI
  3. Falls back to Anthropic if ANTHROPIC_API_KEY is set, else OpenAI
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.logging import get_logger
from isa_cad.agent.tools import (
    CalibrationDataTool,
    ComponentLookupTool,
    FreshnessCheckTool,
    GraphTraversalTool,
    SchemaValidationTool,
)
from isa_cad.config.settings import settings
from isa_cad.core.freshness_engine import FreshnessReport
from isa_cad.core.models.enums import ReviewerStatus, ReviewerType
from isa_cad.core.models.reviewer import ReviewerOutput
from isa_cad.state.canvas_state import ComponentGraph


def _build_llm(provider: str | None = None) -> BaseChatModel:
    """
    Construct the chat model based on provider preference and available keys.

    Supported providers: "anthropic" | "openai"
    Falls back automatically when only one API key is present.
    """
    effective = provider or settings.LLM_PROVIDER

    if effective == "openai" or (
        effective not in ("anthropic", "openai") and not settings.ANTHROPIC_API_KEY
    ):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.0,
            api_key=settings.OPENAI_API_KEY or None,
        )

    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=settings.ANTHROPIC_MODEL,
        temperature=0.0,
        api_key=settings.ANTHROPIC_API_KEY or None,
        max_tokens=2048,
    )


def _build_tools(
    graph: ComponentGraph | None,
    freshness: FreshnessReport | None,
) -> list:
    """Instantiate all five tools with injected data from state."""
    g = graph or ComponentGraph()
    fr = freshness or FreshnessReport()
    return [
        GraphTraversalTool(resolved_graph=g),
        ComponentLookupTool(resolved_graph=g),
        SchemaValidationTool(),
        FreshnessCheckTool(freshness_report=fr),
        CalibrationDataTool(),
    ]


def _state_to_context(state: AgentState) -> str:
    """
    Serialise the relevant parts of AgentState into a human-readable
    context string to pass as the HumanMessage.
    """
    parts: list[str] = []

    source = state.get("source_component_id") or "unknown"
    parts.append(f"Source component: {source}")

    baseline = state.get("baseline_ref") or state.get("canvas_session") and getattr(
        state.get("canvas_session"), "baseline_ref", ""
    ) or ""
    if baseline:
        parts.append(f"Baseline ref: {baseline}")

    goal = state.get("optimization_goal")
    if goal:
        parts.append(f"Optimization goal: {goal.value if hasattr(goal, 'value') else goal}")

    delta: dict[str, Any] = state.get("design_delta") or {}
    if delta:
        parts.append(f"Design delta: {json.dumps(delta, default=str)[:800]}")

    graph: ComponentGraph | None = state.get("resolved_graph")
    if graph:
        node_ids = [n.id for n in graph.nodes]
        parts.append(f"Graph nodes ({len(node_ids)}): {', '.join(node_ids[:20])}")

    return "\n".join(parts)


class LLMReviewerBase(ABC):
    """
    Abstract base for all LLM-backed reviewers.

    Subclasses must implement:
        reviewer_type  — ReviewerType enum value
        system_prompt  — domain-specific system prompt string
        _parse_output  — map LLM response dict → concrete ReviewerOutput
        _fallback      — return a DEGRADED ReviewerOutput when LLM fails
    """

    @property
    @abstractmethod
    def reviewer_type(self) -> ReviewerType: ...

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def _parse_output(self, data: dict[str, Any]) -> ReviewerOutput: ...

    @abstractmethod
    def _fallback(self, reason: str) -> ReviewerOutput: ...

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self._llm: BaseChatModel | None = llm   # lazy — built on first call

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = _build_llm()
        return self._llm

    def __call__(self, state: AgentState) -> AgentState:
        log = get_logger(__name__)
        log.info("llm_reviewer.start", reviewer=self.reviewer_type.value)
        try:
            output = self._review(state)
            log.info(
                "llm_reviewer.done",
                reviewer=self.reviewer_type.value,
                status=output.status.value,
                score=round(output.score, 4),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("llm_reviewer.failed", reviewer=self.reviewer_type.value, error=str(exc))
            output = self._fallback(f"LLM call failed: {exc}")

        key_map = {
            ReviewerType.COST:        "cost_review",
            ReviewerType.PERFORMANCE: "performance_review",
            ReviewerType.SECURITY:    "security_review",
        }
        return {**state, key_map[self.reviewer_type]: output}

    def _review(self, state: AgentState) -> ReviewerOutput:
        graph     = state.get("resolved_graph")
        freshness = state.get("freshness_report")
        tools     = _build_tools(graph, freshness)

        llm = self._get_llm()
        llm_with_tools = llm.bind_tools(tools)

        context = _state_to_context(state)
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=context),
        ]

        response = llm_with_tools.invoke(messages)

        # Try to extract structured JSON from the response
        data = self._extract_json(response)
        if data is None:
            return self._fallback("Could not extract structured JSON from LLM response.")

        return self._parse_output(data)

    def _extract_json(self, response: Any) -> dict[str, Any] | None:
        """
        Extract a JSON dict from the LLM response.

        Tries (in order):
          1. response.content if it is a dict (structured output)
          2. JSON parsing of response.content string
          3. First code-block ``` json ... ``` in the content
        """
        content = getattr(response, "content", None)

        if isinstance(content, dict):
            return content

        if isinstance(content, str):
            # Direct JSON
            stripped = content.strip()
            if stripped.startswith("{"):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass

            # Fenced code block
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

        return None
