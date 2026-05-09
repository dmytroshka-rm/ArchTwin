from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from isa_cad.config.settings import settings
from isa_cad.core.models.enums import CacheContext


# ── CHR heuristic table (Section 3.2) ────────────────────────────────────────

CHR_HEURISTICS: dict[CacheContext, float] = {
    CacheContext.CDN:            settings.CHR_CDN_DEFAULT,    # 0.85
    CacheContext.INTERNAL_CACHE: settings.CHR_INTERNAL_CACHE, # 0.70
    CacheContext.UNKNOWN:        settings.CHR_UNKNOWN,         # 0.00
}

# Confidence impact per cache context (Section 3.2 table)
CHR_CONFIDENCE_IMPACT: dict[CacheContext, str] = {
    CacheContext.CDN:            "medium",  # medium if cacheable; low if headers unknown
    CacheContext.INTERNAL_CACHE: "medium",  # medium only if access pattern is read-heavy
    CacheContext.UNKNOWN:        "low",     # conservative; shown in Fidelity Report
}


class ConfidenceImpact(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


# ── Input / Output dataclasses ────────────────────────────────────────────────

@dataclass
class EgressCostInput:
    """
    Input for cache-aware egress cost calculation.
    Section 3.2:  cost = monthly_gb * (1 - CHR) * egress_rate
    """
    monthly_gb: float                          # total monthly data transfer in GB
    egress_rate_per_gb: float                  # USD per GB egress

    # CHR source — provide one of:
    cache_context: CacheContext | None = None  # use heuristic default
    observed_chr: float | None = None          # use real observed value (0.0–1.0)

    # Optional — inter-region data (same formula, different rate)
    inter_region_gb: float = 0.0
    inter_region_rate_per_gb: float = 0.0


@dataclass
class EgressCostResult:
    """
    Result of cache-aware egress cost calculation.
    Every heuristic is flagged as assumption and reduces confidence.
    """
    # Core outputs
    effective_chr: float           # CHR actually used in calculation
    chr_source: str                # "observed" | "heuristic_cdn_default" | …
    is_assumption: bool            # True when CHR is heuristic, not observed

    billable_gb: float             # monthly_gb * (1 - CHR)
    egress_cost_usd: float         # billable_gb * egress_rate

    inter_region_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    confidence_impact: ConfidenceImpact = ConfidenceImpact.MEDIUM
    confidence_penalty: float = 0.0   # how much to subtract from base confidence

    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ResourceCostInput:
    """
    Input for a single cloud resource cost item.
    """
    resource_id: str
    resource_type: str          # "compute", "storage", "db", "queue", "network"
    unit_price_usd: float       # price per unit per month
    quantity: float             # number of units
    unit: str = ""              # e.g. "vCPU-hour", "GB", "million requests"
    is_estimated: bool = False


@dataclass
class TCOInput:
    """
    Full TCO calculation input.
    """
    resources: list[ResourceCostInput] = field(default_factory=list)
    egress: EgressCostInput | None = None
    request_fees_usd: float = 0.0          # e.g. Lambda invocations, API Gateway
    operational_overhead_usd: float = 0.0  # support, tooling overhead
    safety_buffer_multiplier: float = 1.0  # from CalibrationResult (1.0 or 1.15)


@dataclass
class TCOResult:
    """
    Full TCO breakdown.
    """
    resource_cost_usd: float
    egress_result: EgressCostResult | None
    request_fees_usd: float
    operational_overhead_usd: float

    subtotal_usd: float          # before safety buffer
    safety_buffer_applied: bool
    safety_buffer_multiplier: float
    total_usd: float             # after safety buffer

    resource_breakdown: list[dict] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── Calculator ────────────────────────────────────────────────────────────────

class CostCalculator:
    """
    Implements cache-aware costing from Section 3.2 of the convention.

    cost = monthly_gb * (1 - CHR) * egress_rate

    CHR heuristic defaults (must be marked as Assumption):
        CDN / CloudFront / Cloudflare:   CHR = 0.85
        Redis / Memcached internal:      CHR = 0.70
        Unknown / no cache metrics:      CHR = 0.00  (conservative)
    """

    def compute_egress(self, inp: EgressCostInput) -> EgressCostResult:
        """
        Compute cache-aware egress cost.
        Resolves CHR from observed value or heuristic, marks assumptions.
        """
        effective_chr, chr_source, is_assumption, penalty, ci, assumptions = (
            self._resolve_chr(inp)
        )

        billable_gb    = inp.monthly_gb * (1.0 - effective_chr)
        egress_cost    = round(billable_gb * inp.egress_rate_per_gb, 4)
        inter_cost     = round(inp.inter_region_gb * inp.inter_region_rate_per_gb, 4)
        total          = round(egress_cost + inter_cost, 4)

        notes: list[str] = []
        if inp.inter_region_gb > 0:
            notes.append(
                f"Inter-region transfer: {inp.inter_region_gb} GB "
                f"× ${inp.inter_region_rate_per_gb}/GB = ${inter_cost}/mo"
            )

        return EgressCostResult(
            effective_chr=round(effective_chr, 4),
            chr_source=chr_source,
            is_assumption=is_assumption,
            billable_gb=round(billable_gb, 4),
            egress_cost_usd=egress_cost,
            inter_region_cost_usd=inter_cost,
            total_cost_usd=total,
            confidence_impact=ci,
            confidence_penalty=penalty,
            assumptions=assumptions,
            notes=notes,
        )

    def compute_tco(self, inp: TCOInput) -> TCOResult:
        """
        Compute full TCO: resources + egress + request fees + overhead + safety buffer.
        """
        resource_total = 0.0
        breakdown: list[dict] = []
        assumptions: list[str] = []
        notes: list[str] = []

        for r in inp.resources:
            line_total = round(r.unit_price_usd * r.quantity, 4)
            resource_total += line_total
            breakdown.append({
                "resource_id":   r.resource_id,
                "resource_type": r.resource_type,
                "unit_price":    r.unit_price_usd,
                "quantity":      r.quantity,
                "unit":          r.unit,
                "line_total":    line_total,
                "is_estimated":  r.is_estimated,
            })
            if r.is_estimated:
                assumptions.append(f"{r.resource_id}: price is estimated, not from live pricebook")

        egress_result: EgressCostResult | None = None
        egress_cost = 0.0
        if inp.egress is not None:
            egress_result = self.compute_egress(inp.egress)
            egress_cost   = egress_result.total_cost_usd
            assumptions.extend(egress_result.assumptions)
            notes.extend(egress_result.notes)

        subtotal = round(
            resource_total
            + egress_cost
            + inp.request_fees_usd
            + inp.operational_overhead_usd,
            4,
        )

        buffer_applied = inp.safety_buffer_multiplier > 1.0
        total = round(subtotal * inp.safety_buffer_multiplier, 4)

        if buffer_applied:
            notes.append(
                f"Safety buffer ×{inp.safety_buffer_multiplier} applied "
                f"(+{round((inp.safety_buffer_multiplier - 1) * 100, 1)}%). "
                f"Subtotal ${subtotal} → Total ${total}"
            )

        return TCOResult(
            resource_cost_usd=round(resource_total, 4),
            egress_result=egress_result,
            request_fees_usd=inp.request_fees_usd,
            operational_overhead_usd=inp.operational_overhead_usd,
            subtotal_usd=subtotal,
            safety_buffer_applied=buffer_applied,
            safety_buffer_multiplier=inp.safety_buffer_multiplier,
            total_usd=total,
            resource_breakdown=breakdown,
            assumptions=assumptions,
            notes=notes,
        )

    def tco_delta(
        self,
        baseline: TCOResult,
        proposed: TCOResult,
    ) -> dict:
        """
        Compute cost delta between baseline and a proposed layer.
        Returns a summary dict for the Trade-off Matrix.
        """
        delta_usd    = round(proposed.total_usd - baseline.total_usd, 4)
        delta_pct    = (
            round(delta_usd / baseline.total_usd * 100, 2)
            if baseline.total_usd > 0
            else 0.0
        )
        return {
            "baseline_usd":  baseline.total_usd,
            "proposed_usd":  proposed.total_usd,
            "delta_usd":     delta_usd,
            "delta_pct":     delta_pct,
            "is_saving":     delta_usd < 0,
            "assumptions":   proposed.assumptions,
        }

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_chr(
        inp: EgressCostInput,
    ) -> tuple[float, str, bool, float, ConfidenceImpact, list[str]]:
        """
        Resolve effective CHR, source label, assumption flag,
        confidence penalty and assumption messages.

        Returns: (chr, source, is_assumption, penalty, confidence_impact, assumptions)
        """
        assumptions: list[str] = []

        if inp.observed_chr is not None:
            # Real observed metric — no penalty
            chr_val = max(0.0, min(1.0, inp.observed_chr))
            return (chr_val, "observed", False, 0.0, ConfidenceImpact.HIGH, assumptions)

        # Use heuristic default
        context = inp.cache_context or CacheContext.UNKNOWN
        chr_val = CHR_HEURISTICS[context]
        ci_str  = CHR_CONFIDENCE_IMPACT[context]
        ci      = ConfidenceImpact(ci_str)

        # Confidence penalties per context
        penalty_map = {
            CacheContext.CDN:            0.05,
            CacheContext.INTERNAL_CACHE: 0.05,
            CacheContext.UNKNOWN:        0.15,   # conservative unknown → large penalty
        }
        penalty = penalty_map[context]

        source_labels = {
            CacheContext.CDN:            "heuristic_cdn_default",
            CacheContext.INTERNAL_CACHE: "heuristic_internal_cache_default",
            CacheContext.UNKNOWN:        "heuristic_unknown_conservative",
        }
        source = source_labels[context]

        msg_map = {
            CacheContext.CDN: (
                f"CDN CHR default used (CHR={chr_val}): "
                "real cache metrics unavailable. Mark as Assumption."
            ),
            CacheContext.INTERNAL_CACHE: (
                f"Internal cache CHR default used (CHR={chr_val}): "
                "assumes read-heavy access pattern. Mark as Assumption."
            ),
            CacheContext.UNKNOWN: (
                f"No cache context provided — conservative CHR=0.00 assumed. "
                "All egress treated as billable. Mark as Assumption."
            ),
        }
        assumptions.append(msg_map[context])

        return (chr_val, source, True, penalty, ci, assumptions)
