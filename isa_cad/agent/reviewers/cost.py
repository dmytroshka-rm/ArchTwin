from __future__ import annotations

from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.math_models.costing import (
    CostCalculator,
    EgressCostInput,
    ResourceCostInput,
    TCOInput,
    TCOResult,
)
from isa_cad.core.models.base import EvidenceRef
from isa_cad.core.models.enums import (
    CacheContext,
    OptimizationGoal,
    ReviewerStatus,
    ReviewerType,
)
from isa_cad.core.models.reviewer import CostReviewerOutput, Finding
from isa_cad.state.canvas_state import ComponentGraph, ComponentNode


# ── Heuristic pricing table (USD/month) ──────────────────────────────────────
# Used when no observed cost data is available in node.metadata.
# These are conservative representative estimates, always flagged as assumptions.

_COMPONENT_COST_USD: dict[str, float] = {
    "service":   50.0,    # small container / micro-service
    "database": 200.0,    # managed database (RDS/Aurora small)
    "queue":     10.0,    # managed queue (SQS / SNS)
    "gateway":   30.0,    # API Gateway
    "external":   0.0,    # 3rd-party — no direct cost assumed
    "logging":    5.0,    # log aggregator / shipping
    "cache":     30.0,    # Redis / Memcached small
    "storage":   20.0,    # object storage (S3 ~200 GB)
    "lambda":     2.0,    # serverless function (low invocation)
}

# Default CHR per component type for egress estimation
_COMPONENT_CHR: dict[str, tuple[CacheContext, float]] = {
    "service":   (CacheContext.UNKNOWN, 0.0),
    "database":  (CacheContext.UNKNOWN, 0.0),
    "queue":     (CacheContext.UNKNOWN, 0.0),
    "gateway":   (CacheContext.CDN, 0.85),
    "external":  (CacheContext.UNKNOWN, 0.0),
    "logging":   (CacheContext.UNKNOWN, 0.0),
    "cache":     (CacheContext.INTERNAL_CACHE, 0.70),
    "storage":   (CacheContext.CDN, 0.85),
    "lambda":    (CacheContext.UNKNOWN, 0.0),
}

# Assumed monthly egress per component type in GB
_COMPONENT_EGRESS_GB: dict[str, float] = {
    "service":   10.0,
    "database":   2.0,
    "queue":      1.0,
    "gateway":   50.0,
    "external":   0.0,
    "logging":    5.0,
    "cache":      3.0,
    "storage":   20.0,
    "lambda":     5.0,
}

# Standard egress rate per GB (AWS us-east-1 representative)
_EGRESS_RATE_PER_GB = 0.09
_INTER_REGION_RATE_PER_GB = 0.02


def _node_monthly_cost(node: ComponentNode) -> float:
    """
    Resolve monthly resource cost for a node.
    Checks node.metadata['monthly_cost_usd'] first; falls back to heuristic.
    """
    if "monthly_cost_usd" in node.metadata:
        return float(node.metadata["monthly_cost_usd"])
    return _COMPONENT_COST_USD.get(node.component_type, 50.0)


def _node_egress_gb(node: ComponentNode) -> float:
    """Resolve monthly egress GB for a node (metadata or heuristic)."""
    if "monthly_egress_gb" in node.metadata:
        return float(node.metadata["monthly_egress_gb"])
    return _COMPONENT_EGRESS_GB.get(node.component_type, 10.0)


def _node_cache_context(node: ComponentNode) -> CacheContext:
    """Resolve CacheContext for a node."""
    if "cache_context" in node.metadata:
        try:
            return CacheContext(node.metadata["cache_context"])
        except ValueError:
            pass
    ctx, _ = _COMPONENT_CHR.get(node.component_type, (CacheContext.UNKNOWN, 0.0))
    return ctx


def _build_tco_input(
    graph: ComponentGraph,
    safety_buffer: float = 1.0,
) -> TCOInput:
    """
    Convert a ComponentGraph into a TCOInput using heuristic cost table.
    All estimated values are flagged via ResourceCostInput.is_estimated=True.
    """
    resources: list[ResourceCostInput] = []
    total_egress_gb = 0.0
    total_inter_region_gb = 0.0
    cache_context_dominant = CacheContext.UNKNOWN

    for node in graph.nodes:
        monthly = _node_monthly_cost(node)
        is_estimated = "monthly_cost_usd" not in node.metadata
        resources.append(ResourceCostInput(
            resource_id=node.id,
            resource_type=node.component_type,
            unit_price_usd=monthly,
            quantity=1.0,
            unit="month",
            is_estimated=is_estimated,
        ))

        eg = _node_egress_gb(node)
        total_egress_gb += eg

        inter = float(node.metadata.get("inter_region_gb", 0.0))
        total_inter_region_gb += inter

        ctx = _node_cache_context(node)
        # Prefer CDN > INTERNAL > UNKNOWN for dominant context
        if ctx == CacheContext.CDN:
            cache_context_dominant = CacheContext.CDN
        elif ctx == CacheContext.INTERNAL_CACHE and cache_context_dominant != CacheContext.CDN:
            cache_context_dominant = CacheContext.INTERNAL_CACHE

    observed_chr: float | None = None
    if any("observed_chr" in n.metadata for n in graph.nodes):
        # Use average of all observed CHR values
        chrs = [
            float(n.metadata["observed_chr"])
            for n in graph.nodes
            if "observed_chr" in n.metadata
        ]
        observed_chr = sum(chrs) / len(chrs)

    egress_input = EgressCostInput(
        monthly_gb=total_egress_gb,
        egress_rate_per_gb=_EGRESS_RATE_PER_GB,
        cache_context=cache_context_dominant,
        observed_chr=observed_chr,
        inter_region_gb=total_inter_region_gb,
        inter_region_rate_per_gb=_INTER_REGION_RATE_PER_GB,
    )

    return TCOInput(
        resources=resources,
        egress=egress_input,
        safety_buffer_multiplier=safety_buffer,
    )


def _score_from_delta_pct(delta_pct: float, goal: OptimizationGoal) -> float:
    """
    Map cost delta % to a reviewer score [0.0, 1.0].
    Negative delta = cost saving = better score.
    Goal COST_EFFICIENCY amplifies the weight.
    """
    # Clamp delta to [-100%, +200%]
    clamped = max(-100.0, min(200.0, delta_pct))

    # Base score: linear mapping, 0% delta → 0.5, -50% → 0.9, +50% → 0.1
    base = 0.5 - (clamped / 100.0) * 0.4

    if goal == OptimizationGoal.COST_EFFICIENCY:
        # Amplify: savings rewarded more, overruns penalised more
        base = 0.5 - (clamped / 100.0) * 0.5

    return round(max(0.0, min(1.0, base)), 4)


def _status_from_delta_pct(delta_pct: float) -> ReviewerStatus:
    if delta_pct <= 5.0:
        return ReviewerStatus.PASS
    if delta_pct <= 25.0:
        return ReviewerStatus.WARNING
    return ReviewerStatus.FAIL


class CostReviewerNode:
    """
    LangGraph node — runs in parallel with Performance and Security reviewers.

    Computes:
        • Baseline TCO  (from baseline_graph)
        • Proposed TCO  (from resolved_graph)
        • TCO delta, egress breakdown, CHR source
        • CostReviewerOutput written to state["cost_review"]

    All heuristic costs and CHR values are flagged as Assumptions per
    Section 3.2 and the No Silent Mutation / Metadata First conventions.
    """

    _calculator = CostCalculator()

    def __call__(self, state: AgentState) -> AgentState:
        session   = state.get("canvas_session")
        resolved  = state.get("resolved_graph")
        cal_result = state.get("calibration_result")
        goal       = state.get("optimization_goal", OptimizationGoal.BALANCED)

        if session is None or resolved is None:
            output = CostReviewerOutput(
                status=ReviewerStatus.UNKNOWN,
                score=0.5,
                confidence=0.0,
                recommendation="No session or graph available for cost analysis.",
                missing_inputs=["canvas_session", "resolved_graph"],
            )
            return {**state, "cost_review": output}

        safety_buffer = (
            cal_result.safety_buffer.cost_multiplier
            if cal_result and cal_result.safety_buffer.applied
            else 1.0
        )

        baseline_graph = session.baseline_graph
        proposed_graph = resolved

        baseline_tco = self._calculator.compute_tco(
            _build_tco_input(baseline_graph, safety_buffer=1.0)
        )
        proposed_tco = self._calculator.compute_tco(
            _build_tco_input(proposed_graph, safety_buffer=safety_buffer)
        )

        delta = self._calculator.tco_delta(baseline_tco, proposed_tco)
        delta_pct  = delta["delta_pct"]
        delta_usd  = delta["delta_usd"]

        status     = _status_from_delta_pct(delta_pct)
        score      = _score_from_delta_pct(delta_pct, goal)
        confidence = self._compute_confidence(baseline_tco, proposed_tco)

        findings   = self._build_findings(delta, baseline_tco, proposed_tco)
        evidence   = self._build_evidence(baseline_tco, proposed_tco)
        assumptions = list(dict.fromkeys(
            baseline_tco.assumptions + proposed_tco.assumptions
        ))

        egress_result   = proposed_tco.egress_result
        chr_source      = egress_result.chr_source      if egress_result else None
        effective_chr   = egress_result.effective_chr   if egress_result else None
        egress_monthly  = egress_result.total_cost_usd  if egress_result else None
        inter_region    = (
            egress_result.inter_region_cost_usd if egress_result else None
        )

        recommendation = self._build_recommendation(
            delta_pct, delta_usd, status, goal, safety_buffer,
        )

        output = CostReviewerOutput(
            status=status,
            score=score,
            confidence=confidence,
            findings=findings,
            evidence=evidence,
            assumptions=assumptions,
            recommendation=recommendation,
            monthly_current_usd=baseline_tco.total_usd,
            monthly_projected_usd=proposed_tco.total_usd,
            egress_monthly_usd=egress_monthly,
            cache_hit_ratio=effective_chr,
            cache_hit_ratio_source=chr_source,
            inter_region_cost_usd=inter_region,
            request_fees_usd=proposed_tco.request_fees_usd,
            tco_delta_usd=delta_usd,
        )

        return {**state, "cost_review": output}

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(baseline: TCOResult, proposed: TCOResult) -> float:
        """
        Confidence = 1.0 reduced by:
          • 0.15 per assumption in proposed costs (CHR heuristics, estimated prices)
          • capped minimum 0.20
        """
        penalty_per = 0.08
        n_assumptions = len(set(proposed.assumptions))
        confidence = max(0.20, 1.0 - (n_assumptions * penalty_per))
        # If safety buffer was applied, cap at 0.85 (uncertainty acknowledged)
        if proposed.safety_buffer_applied:
            confidence = min(confidence, 0.85)
        return round(confidence, 4)

    @staticmethod
    def _build_findings(
        delta: dict[str, Any],
        baseline: TCOResult,
        proposed: TCOResult,
    ) -> list[Finding]:
        findings: list[Finding] = []
        delta_usd = delta["delta_usd"]
        delta_pct = delta["delta_pct"]

        if delta["is_saving"]:
            findings.append(Finding(
                severity="info",
                title="Cost reduction detected",
                description=(
                    f"Proposed architecture reduces monthly cost by "
                    f"${abs(delta_usd):.2f} ({abs(delta_pct):.1f}%)."
                ),
                recommendation="Proceed — cost efficiency improved.",
            ))
        elif delta_pct > 25.0:
            findings.append(Finding(
                severity="high",
                title="Significant cost increase",
                description=(
                    f"Proposed architecture increases monthly cost by "
                    f"${delta_usd:.2f} ({delta_pct:.1f}%). "
                    "Exceeds 25% threshold."
                ),
                recommendation=(
                    "Review added components for cost optimisation. "
                    "Consider Reserved Instances or right-sizing."
                ),
            ))
        elif delta_pct > 5.0:
            findings.append(Finding(
                severity="medium",
                title="Moderate cost increase",
                description=(
                    f"Monthly cost increases by ${delta_usd:.2f} ({delta_pct:.1f}%)."
                ),
                recommendation="Acceptable if aligned with performance or reliability goals.",
            ))

        # Egress findings
        if proposed.egress_result and proposed.egress_result.is_assumption:
            findings.append(Finding(
                severity="low",
                title="Egress cost is estimated (CHR heuristic)",
                description=(
                    f"Cache Hit Ratio source: {proposed.egress_result.chr_source}. "
                    f"Effective CHR={proposed.egress_result.effective_chr:.2f}. "
                    "Real observed metrics unavailable."
                ),
                recommendation=(
                    "Instrument CDN / cache metrics and re-run with observed_chr "
                    "to improve egress cost accuracy."
                ),
            ))

        # Safety buffer finding
        if proposed.safety_buffer_applied:
            findings.append(Finding(
                severity="low",
                title="Safety buffer applied to projected cost",
                description=(
                    f"Calibration safety buffer ×{proposed.safety_buffer_multiplier} "
                    f"applied. Subtotal ${proposed.subtotal_usd:.2f} → "
                    f"Total ${proposed.total_usd:.2f}."
                ),
                recommendation=(
                    "Collect more actuals to narrow the safety buffer "
                    "and reduce cost uncertainty."
                ),
            ))

        return findings

    @staticmethod
    def _build_evidence(baseline: TCOResult, proposed: TCOResult) -> list[EvidenceRef]:
        evidence: list[EvidenceRef] = []

        evidence.append(EvidenceRef(
            source="heuristic_cost_table",
            description="Monthly resource cost estimated from component_type heuristic table.",
            value={
                "baseline_resource_usd": baseline.resource_cost_usd,
                "proposed_resource_usd": proposed.resource_cost_usd,
            },
            is_assumption=any(
                r["is_estimated"] for r in proposed.resource_breakdown
            ),
        ))

        if proposed.egress_result:
            evidence.append(EvidenceRef(
                source=proposed.egress_result.chr_source,
                description=(
                    f"Egress CHR={proposed.egress_result.effective_chr:.2f} "
                    f"({'observed' if not proposed.egress_result.is_assumption else 'heuristic'}). "
                    f"Billable GB={proposed.egress_result.billable_gb:.2f}."
                ),
                value=proposed.egress_result.egress_cost_usd,
                is_assumption=proposed.egress_result.is_assumption,
            ))

        return evidence

    @staticmethod
    def _build_recommendation(
        delta_pct: float,
        delta_usd: float,
        status: ReviewerStatus,
        goal: OptimizationGoal,
        safety_buffer: float,
    ) -> str:
        direction = "reduces" if delta_usd < 0 else "increases"
        sign      = "-" if delta_usd < 0 else "+"
        buf_note  = (
            f" (×{safety_buffer} safety buffer applied)"
            if safety_buffer > 1.0
            else ""
        )

        if status == ReviewerStatus.PASS:
            return (
                f"Cost impact is acceptable: {sign}${abs(delta_usd):.2f}/mo "
                f"({sign}{abs(delta_pct):.1f}%){buf_note}. "
                f"Proposal {direction} monthly spend."
            )
        if status == ReviewerStatus.WARNING:
            return (
                f"Moderate cost increase: {sign}${abs(delta_usd):.2f}/mo "
                f"({sign}{abs(delta_pct):.1f}%){buf_note}. "
                "Review if aligned with non-cost goals."
            )
        return (
            f"Cost review FAIL: +${delta_usd:.2f}/mo (+{delta_pct:.1f}%){buf_note}. "
            "Significant overrun — architect must justify or redesign."
        )
