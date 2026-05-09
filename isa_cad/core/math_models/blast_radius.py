from __future__ import annotations

from dataclasses import dataclass, field

from isa_cad.config.settings import settings
from isa_cad.core.models.blast_radius import BlastRadiusOutput, ImpactedComponent
from isa_cad.core.models.enums import ComponentTier
from isa_cad.state.canvas_state import ComponentGraph, ComponentNode


# ── Tier → criticality multiplier map (Section 9) ────────────────────────────

TIER_MULTIPLIER: dict[ComponentTier, float] = {
    ComponentTier.TIER_1:    settings.CRITICALITY_TIER_1,     # 2.0
    ComponentTier.STANDARD:  settings.CRITICALITY_STANDARD,   # 1.0
    ComponentTier.AUXILIARY: settings.CRITICALITY_AUXILIARY,  # 0.5
}

# Default base_impact for a directly-modified component (distance=1 neighbour)
DEFAULT_BASE_IMPACT = 1.0


# ── Risk classifier ───────────────────────────────────────────────────────────

def _classify_risk(
    node: ComponentNode,
    impact_score: float,
    distance: int,
) -> tuple[str, list[str]]:
    """
    Return (risk_label, mitigations) based on component type and impact score.
    Provides sensible defaults; callers can override.
    """
    ctype = node.component_type.lower()
    tier  = node.tier.lower()

    risk = "increased_load"
    mitigations: list[str] = []

    if "db" in ctype or "database" in ctype or "postgresql" in ctype or "mysql" in ctype:
        risk = "potential_io_bottleneck"
        mitigations = [
            "validate peak write TPS against new topology",
            "add connection pooling proxy if not present",
            "set concurrency cap on upstream service",
        ]
    elif "auth" in ctype or "identity" in node.id.lower() or "auth" in node.id.lower():
        risk = "auth_latency_amplification"
        mitigations = [
            "cache token introspection results",
            "define fallback policy for auth service degradation",
        ]
    elif "queue" in ctype or "broker" in ctype or "kafka" in ctype:
        risk = "queue_backpressure"
        mitigations = [
            "review consumer concurrency limits",
            "add dead-letter queue",
            "monitor consumer lag",
        ]
    elif "gateway" in ctype or "api" in ctype:
        risk = "routing_pressure"
        mitigations = [
            "review rate limits and circuit breakers",
            "validate timeout configuration",
        ]
    elif "log" in ctype or "metric" in ctype or "monitor" in ctype:
        risk = "observability_overhead"
        mitigations = [
            "verify log volume stays within budget",
            "check alerting thresholds",
        ]

    if tier == "tier_1" and impact_score >= 2.0:
        mitigations.insert(0, "PRIORITY: high-impact Tier-1 component — review before merge")

    return risk, mitigations


# ── Traversal engine ──────────────────────────────────────────────────────────

@dataclass
class BlastRadiusInput:
    """Input for the Tier-Aware Blast Radius traversal."""
    source_component_id: str          # the component being modified/added
    graph: ComponentGraph             # resolved graph (baseline + active layers)
    max_depth: int = 3                # how deep to traverse (convention default: 3)
    base_impact: float = DEFAULT_BASE_IMPACT
    # Optional: override risk/mitigations per component id
    risk_overrides: dict[str, tuple[str, list[str]]] = field(default_factory=dict)


class BlastRadiusCalculator:
    """
    Tier-Aware Blast Radius traversal.

    Formula (Section 3.3):
        impact_score = (base_impact * C_m) * 0.5 ** (d - 1)

    where:
        d   = graph distance from the modified component
        C_m = criticality_multiplier based on component tier

    Interpretation:
        L1 (d=1) → 100% of (base_impact * C_m)
        L2 (d=2) →  50% of (base_impact * C_m)
        L3 (d=3) →  25% of (base_impact * C_m)
        Tier-1 doubles the result via C_m = 2.0
    """

    def compute(self, inp: BlastRadiusInput) -> BlastRadiusOutput:
        """
        BFS from source_component_id, compute impact for every reachable node,
        build ImpactedComponent list, return BlastRadiusOutput.
        """
        distances = inp.graph.bfs_distances(
            inp.source_component_id,
            max_depth=inp.max_depth,
        )

        impacted: list[ImpactedComponent] = []

        for node_id, distance in sorted(distances.items(), key=lambda x: x[1]):
            node = inp.graph.get_node(node_id)
            if node is None:
                continue

            tier     = _parse_tier(node.tier)
            c_m      = TIER_MULTIPLIER[tier]
            score    = round((inp.base_impact * c_m) * (0.5 ** (distance - 1)), 4)

            if node_id in inp.risk_overrides:
                risk, mitigations = inp.risk_overrides[node_id]
            else:
                risk, mitigations = _classify_risk(node, score, distance)

            impacted.append(
                ImpactedComponent(
                    id=node_id,
                    tier=tier,
                    distance=distance,
                    criticality_multiplier=c_m,
                    impact_score=score,
                    risk=risk,
                    mitigations=mitigations,
                )
            )

        summary = _build_summary(inp.source_component_id, impacted)

        return BlastRadiusOutput(
            source_component_id=inp.source_component_id,
            max_traversal_depth=inp.max_depth,
            impacted_stable_components=impacted,
            summary=summary,
        )

    def diff(
        self,
        baseline_output: BlastRadiusOutput,
        proposed_output: BlastRadiusOutput,
    ) -> dict:
        """
        Compare two BlastRadiusOutputs (baseline vs proposed layer).
        Returns a diff dict for the Trade-off Matrix.
        """
        base_ids = {c.id for c in baseline_output.impacted_stable_components}
        prop_ids = {c.id for c in proposed_output.impacted_stable_components}

        new_components   = prop_ids - base_ids
        removed_components = base_ids - prop_ids
        common_components  = base_ids & prop_ids

        score_changes: list[dict] = []
        for cid in common_components:
            b = next(c for c in baseline_output.impacted_stable_components if c.id == cid)
            p = next(c for c in proposed_output.impacted_stable_components  if c.id == cid)
            delta = round(p.impact_score - b.impact_score, 4)
            if delta != 0:
                score_changes.append({
                    "id": cid,
                    "baseline_score": b.impact_score,
                    "proposed_score": p.impact_score,
                    "delta": delta,
                })

        return {
            "baseline_total":  baseline_output.total_impact_score,
            "proposed_total":  proposed_output.total_impact_score,
            "total_delta":     round(
                proposed_output.total_impact_score - baseline_output.total_impact_score, 4
            ),
            "new_components":     sorted(new_components),
            "removed_components": sorted(removed_components),
            "score_changes":      score_changes,
            "high_risk_delta":    (
                proposed_output.high_risk_count - baseline_output.high_risk_count
            ),
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_tier(tier_str: str) -> ComponentTier:
    """Map a node's tier string to ComponentTier enum, defaulting to STANDARD."""
    mapping = {
        "tier_1":    ComponentTier.TIER_1,
        "tier1":     ComponentTier.TIER_1,
        "standard":  ComponentTier.STANDARD,
        "auxiliary": ComponentTier.AUXILIARY,
        "aux":       ComponentTier.AUXILIARY,
    }
    return mapping.get(tier_str.lower(), ComponentTier.STANDARD)


def _build_summary(source_id: str, impacted: list[ImpactedComponent]) -> str:
    if not impacted:
        return f"No stable components impacted by changes to '{source_id}'."

    tier1_count = sum(1 for c in impacted if c.tier == ComponentTier.TIER_1)
    total_score = round(sum(c.impact_score for c in impacted), 4)
    severity    = "HIGH" if tier1_count > 0 else "MEDIUM" if len(impacted) > 2 else "LOW"

    return (
        f"Blast radius from '{source_id}': "
        f"{len(impacted)} component(s) impacted "
        f"(Tier-1: {tier1_count}), "
        f"total impact score {total_score}. "
        f"Severity: {severity}."
    )
