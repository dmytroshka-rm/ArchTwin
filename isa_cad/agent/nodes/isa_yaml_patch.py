from __future__ import annotations

from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.checkpoint import Checkpoint
from isa_cad.core.models.proposal import DesignProposal
from isa_cad.core.schema.validator import ValidationResult, validate_isa_yaml


# ── Section builders ─────────────────────────────────────────────────────────

def _comparison_section(proposal: DesignProposal) -> dict:
    section: dict = {"baseline_ref": proposal.baseline_ref}
    if proposal.compare_against:
        section["compare_against"] = list(proposal.compare_against)
    section["differential_mode"] = proposal.differential_mode.value
    return section


def _simulation_fidelity_section(proposal: DesignProposal) -> dict | None:
    sf = proposal.simulation_fidelity
    if sf is None:
        return None
    d: dict = {
        "base_confidence":              sf.base_confidence,
        "data_freshness_score":         sf.data_freshness_score,
        "confidence_penalty":           sf.confidence_penalty,
        "adjusted_confidence":          sf.adjusted_confidence,
        "output_mode":                  sf.output_mode,
        "require_observed_graph_refresh": sf.require_observed_graph_refresh,
    }
    age = {
        k: v for k, v in {
            "cloud_inventory":  sf.data_age.cloud_inventory,
            "runtime_metrics":  sf.data_age.runtime_metrics,
            "pricing_data":     sf.data_age.pricing_data,
            "calibration_data": sf.data_age.calibration_data,
        }.items() if v is not None
    }
    if age:
        d["data_age"] = age
    return d


def _calibration_section(proposal: DesignProposal) -> dict | None:
    cal = proposal.calibration
    if not cal.enabled_for_existing_system and not cal.historical_errors:
        return None
    d: dict = {"enabled_for_existing_system": cal.enabled_for_existing_system}

    # Flatten list[CalibrationError] → {cost: max_delta, latency: max_delta}
    error_delta: dict[str, float] = {}
    for err in cal.historical_errors:
        if err.metric in ("cost", "latency"):
            if err.delta > error_delta.get(err.metric, 0.0):
                error_delta[err.metric] = err.delta
    if error_delta:
        d["historical_error_delta"] = error_delta

    sb = cal.safety_buffer
    if sb.applied or sb.cost_multiplier != 1.0 or sb.latency_multiplier != 1.0:
        d["safety_buffer"] = {
            "applied":            sb.applied,
            "reason":             sb.reason,
            "cost_multiplier":    sb.cost_multiplier,
            "latency_multiplier": sb.latency_multiplier,
            "bias_note":          sb.bias_note,
        }
    return d


def _non_linear_scoring_section(proposal: DesignProposal) -> dict:
    scoring = proposal.scoring
    gate_set = scoring.veto_gates
    return {
        "recommendation_score": scoring.recommendation_score,
        "optimization_weights": {
            "cost":        scoring.optimization_weights.cost,
            "performance": scoring.optimization_weights.performance,
            "reliability": scoring.optimization_weights.reliability,
            "security":    scoring.optimization_weights.security,
        },
        "veto_gates": {
            "security_gate":    gate_set.security_gate.multiplier,
            "reliability_gate": gate_set.reliability_gate.multiplier,
            "compliance_gate":  gate_set.compliance_gate.multiplier,
            "fidelity_gate":    gate_set.fidelity_gate.multiplier,
        },
    }


def _parallel_reviews_section(proposal: DesignProposal) -> dict | None:
    reviews: dict = {}

    if proposal.cost_review is not None:
        cr = proposal.cost_review
        cost: dict = {"status": cr.status.value, "confidence": cr.confidence}
        for field in ("monthly_current_usd", "monthly_projected_usd", "egress_monthly_usd",
                      "cache_hit_ratio", "cache_hit_ratio_source"):
            val = getattr(cr, field, None)
            if val is not None:
                cost[field] = val
        if cr.assumptions:
            cost["assumptions"] = list(cr.assumptions)
        reviews["cost"] = cost

    if proposal.performance_review is not None:
        pr = proposal.performance_review
        perf: dict = {"status": pr.status.value, "confidence": pr.confidence}
        for field in ("latency_delta", "p95_baseline_ms", "p95_projected_ms",
                      "p99_baseline_ms", "p99_projected_ms", "bottleneck_risk",
                      "cold_start_risk", "db_pressure_risk"):
            val = getattr(pr, field, None)
            if val is not None:
                perf[field] = val
        reviews["performance"] = perf

    if proposal.security_review is not None:
        sr = proposal.security_review
        sec: dict = {
            "status":                sr.status.value,
            "confidence":            sr.confidence,
            "pii_flow_status":       sr.pii_flow_status,
            "data_residency_status": sr.data_residency_status,
            "compliance_status":     sr.compliance_status,
        }
        for field in ("public_exposure_risk", "iam_scope_risk"):
            val = getattr(sr, field, None)
            if val is not None:
                sec[field] = val
        reviews["security"] = sec

    return reviews if reviews else None


def _blast_radius_section(proposal: DesignProposal) -> dict | None:
    br = proposal.blast_radius
    if br is None:
        return None
    d: dict = {
        "source_component_id": br.source_component_id,
        "max_traversal_depth": br.max_traversal_depth,
        "summary":             br.summary,
    }
    if br.total_impact_score > 0:
        d["total_impact_score"] = br.total_impact_score
    comps = []
    for c in br.impacted_stable_components:
        comp: dict = {
            "id":                     c.id,
            "tier":                   c.tier.value if hasattr(c.tier, "value") else c.tier,
            "distance":               c.distance,
            "criticality_multiplier": c.criticality_multiplier,
            "impact_score":           c.impact_score,
            "risk":                   c.risk,
        }
        if c.mitigations:
            comp["mitigations"] = list(c.mitigations)
        comps.append(comp)
    if comps:
        d["impacted_stable_components"] = comps
    return d


def _checkpointing_section(
    proposal: DesignProposal,
    checkpoint: Checkpoint | None,
) -> dict:
    if checkpoint is not None:
        d: dict = {
            "checkpoint_required": False,
            "checkpoint_id":       checkpoint.id,
            "resume_node":         checkpoint.resume_node,
            "saved_at":            checkpoint.saved_at.isoformat(),
            "pending_action":      checkpoint.pending_action,
        }
    elif proposal.checkpoint_id is not None:
        d = {
            "checkpoint_required": False,
            "checkpoint_id":       proposal.checkpoint_id,
            "resume_node":         proposal.resume_node,
        }
    else:
        d = {"checkpoint_required": False}
    return d


def _required_actions_section(proposal: DesignProposal) -> dict:
    ra = proposal.required_actions
    return {
        "developer":     list(ra.developer),
        "architect":     list(ra.architect),
        "security_ops":  list(ra.security_ops),
        "data_fidelity": list(ra.data_fidelity),
    }


# ── Main builder ──────────────────────────────────────────────────────────────

def build_proposal_patch(
    proposal: DesignProposal,
    checkpoint: Checkpoint | None = None,
) -> dict[str, Any]:
    """
    Build a schema-valid isa.yaml proposal entry from a DesignProposal.

    Field name mapping (Python → yaml schema):
        proposal.scoring         → non_linear_scoring
        proposal.cost_review … → parallel_reviews.{cost,performance,security}
        proposal.checkpoint_id  → checkpointing block
        proposal.calibration    → calibration (with flattened historical_error_delta)
    """
    patch: dict[str, Any] = {
        "id":               proposal.id,
        "title":            proposal.title,
        "status":           proposal.status.value if hasattr(proposal.status, "value")
                            else str(proposal.status),
        "optimization_goal": proposal.optimization_goal.value,
        "baseline_ref":     proposal.baseline_ref,
    }

    if proposal.canvas_session_id is not None:
        patch["canvas_session_id"] = proposal.canvas_session_id

    patch["comparison"] = _comparison_section(proposal)

    sf = _simulation_fidelity_section(proposal)
    if sf is not None:
        patch["simulation_fidelity"] = sf

    cal = _calibration_section(proposal)
    if cal is not None:
        patch["calibration"] = cal

    patch["non_linear_scoring"] = _non_linear_scoring_section(proposal)

    reviews = _parallel_reviews_section(proposal)
    if reviews is not None:
        patch["parallel_reviews"] = reviews

    br = _blast_radius_section(proposal)
    if br is not None:
        patch["blast_radius"] = br

    patch["checkpointing"] = _checkpointing_section(proposal, checkpoint)
    patch["required_actions"] = _required_actions_section(proposal)

    return patch


# ── LangGraph node ────────────────────────────────────────────────────────────

class IsaYamlPatchNode:
    """
    LangGraph node — generates a validated isa.yaml patch (Section 6.4 / 10).

    Reads the fully-populated DesignProposal from state and emits an
    isa.yaml-compatible dict ready for human review or direct file write.
    Validates the patch against the ISA-CAD JSON Schema before returning.

    Validation errors are non-fatal: the patch is always written to state so
    downstream CLI or output formatters can still use it. Validation warnings
    are captured in final_output["isa_yaml_errors"] for visibility.

    Reads:
        state["proposal"]      — fully populated DesignProposal
        state["checkpoint"]    — Checkpoint | None for checkpointing section
        state["final_output"]  — enriched with patch + validation result (optional)

    Writes:
        state["isa_yaml_patch"]                   — schema-compatible dict
        state["final_output"]["isa_yaml_patch"]   — same dict (if final_output present)
        state["final_output"]["isa_yaml_valid"]   — bool
        state["final_output"]["isa_yaml_errors"]  — list[str]
    """

    def __call__(self, state: AgentState) -> AgentState:
        proposal: DesignProposal | None = state.get("proposal")

        if proposal is None:
            return {**state, "isa_yaml_patch": {}}

        checkpoint: Checkpoint | None = state.get("checkpoint")
        patch = build_proposal_patch(proposal, checkpoint)

        # Validate full document (schema requires design_proposals wrapper)
        validation: ValidationResult = validate_isa_yaml({"design_proposals": [patch]})

        # Enrich final_output if present
        final_output: dict | None = state.get("final_output")
        if final_output is not None:
            final_output = {
                **final_output,
                "isa_yaml_patch":  patch,
                "isa_yaml_valid":  validation.valid,
                "isa_yaml_errors": validation.errors,
            }

        result = {**state, "isa_yaml_patch": patch}
        if final_output is not None:
            result["final_output"] = final_output
        return result
