from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.enums import VetoGateResult, VetoGateType
from isa_cad.core.models.proposal import DesignProposal, RequiredActions
from isa_cad.core.models.veto import VetoGate


# ── Per-signal action generators ─────────────────────────────────────────────

def _gate_actions(gate: VetoGate | None) -> dict[str, list[str]]:
    """
    Map a single veto gate result to persona → action strings.
    Returns empty dict when gate is None or PASSED.
    """
    if gate is None or gate.result == VetoGateResult.PASSED:
        return {}

    gtype = gate.gate_type
    blocked = gate.result == VetoGateResult.BLOCKED
    reason = gate.reason or ""

    if gtype == VetoGateType.SECURITY:
        if blocked:
            return {
                "security_ops": [
                    f"BLOCK — resolve security violations before deployment: {reason}",
                ],
                "developer": [
                    "Fix trust-boundary violations and re-run SecurityReviewerNode.",
                ],
            }
        return {
            "security_ops": [
                f"Review and address security warnings: {reason}",
            ],
        }

    if gtype == VetoGateType.RELIABILITY:
        if blocked:
            return {
                "architect": [
                    f"BLOCK — address critical reliability failure: {reason}",
                ],
                "developer": [
                    "Fix throughput or latency regression identified by PerformanceReviewerNode.",
                ],
            }
        return {
            "architect": [
                f"Review reliability warnings before promoting to production: {reason}",
            ],
        }

    if gtype == VetoGateType.COMPLIANCE:
        if blocked:
            return {
                "data_fidelity": [
                    f"BLOCK — resolve PII / residency compliance failure: {reason}",
                ],
                "security_ops": [
                    "Engage compliance and legal team before deployment.",
                ],
            }
        return {
            "data_fidelity": [
                f"Review data-residency and PII concerns: {reason}",
            ],
        }

    if gtype == VetoGateType.FIDELITY:
        if blocked:
            return {
                "developer": [
                    f"BLOCK — data fidelity too low to make a forecast: {reason}",
                    "Trigger Observed Graph refresh and re-run the pipeline.",
                ],
            }
        return {
            "developer": [
                "Refresh observed-graph data before treating output as a Final Forecast.",
            ],
        }

    return {}


def _blast_radius_actions(state: AgentState) -> dict[str, list[str]]:
    br = state.get("blast_radius")
    if br is None:
        return {}
    actions: dict[str, list[str]] = {}
    if br.high_risk_count > 0:
        actions["architect"] = [
            f"Review {br.high_risk_count} high-risk Tier-1 component(s) in blast radius "
            f"(total impact score: {br.total_impact_score:.2f}).",
        ]
    return actions


def _calibration_actions(state: AgentState) -> dict[str, list[str]]:
    cal = state.get("calibration_loop_output")
    if cal is None:
        return {}
    actions: dict[str, list[str]] = {}
    if cal.human_review_required:
        msg = (
            "Human review required: security false negative detected in calibration history. "
            "Validate SecurityReviewer findings manually."
        )
        actions["security_ops"] = [msg]
        actions["architect"]    = [msg]
    if cal.result.safety_buffer.applied:
        actions.setdefault("architect", []).append(
            "Safety buffer (×1.15) applied to cost/latency estimates — "
            "validate against actual infrastructure data before budgeting."
        )
    return actions


def _merge(base: dict[str, list[str]], extra: dict[str, list[str]]) -> None:
    """Merge extra into base in-place, avoiding duplicate entries."""
    for persona, items in extra.items():
        existing = base.setdefault(persona, [])
        for item in items:
            if item not in existing:
                existing.append(item)


def _build_required_actions(state: AgentState) -> RequiredActions:
    """
    Aggregate per-persona required actions from all signal sources:
      - veto gate results (security, reliability, compliance, fidelity)
      - blast radius high-risk components
      - calibration loop (human review flag, safety buffer)
    """
    accumulated: dict[str, list[str]] = {
        "developer":    [],
        "architect":    [],
        "security_ops": [],
        "data_fidelity": [],
    }

    gate_keys: list[str] = [
        "security_gate",
        "reliability_gate",
        "compliance_gate",
        "fidelity_gate",
    ]
    for key in gate_keys:
        gate: VetoGate | None = state.get(key)  # type: ignore[literal-required]
        _merge(accumulated, _gate_actions(gate))

    _merge(accumulated, _blast_radius_actions(state))
    _merge(accumulated, _calibration_actions(state))

    return RequiredActions(
        developer    = accumulated["developer"],
        architect    = accumulated["architect"],
        security_ops = accumulated["security_ops"],
        data_fidelity = accumulated["data_fidelity"],
    )


class RequiredActionsNode:
    """
    LangGraph node — generates persona-based required actions (Section 6.3).

    Combines signals from veto gates, blast radius, and calibration history
    into four persona buckets:
        developer     — code-level fixes (trust boundaries, latency regression)
        architect     — design decisions (blast radius, reliability, safety buffer)
        security_ops  — security remediation and human-review escalation
        data_fidelity — data governance (PII, residency, compliance)

    Updates ``proposal.required_actions`` in-place and appends
    ``final_output["required_actions"]`` if final_output is present.

    Reads:
        state["security_gate"]            VetoGate (optional)
        state["reliability_gate"]         VetoGate (optional)
        state["compliance_gate"]          VetoGate (optional)
        state["fidelity_gate"]            VetoGate (optional)
        state["blast_radius"]             BlastRadiusOutput (optional)
        state["calibration_loop_output"]  CalibrationLoopOutput (optional)
        state["proposal"]                 DesignProposal (optional)
        state["final_output"]             dict to enrich (optional)

    Writes:
        state["proposal"].required_actions  — updated RequiredActions
        state["final_output"]["required_actions"] — dict copy of actions (if present)
    """

    def __call__(self, state: AgentState) -> AgentState:
        required_actions = _build_required_actions(state)

        # ── attach to proposal ────────────────────────────────────────────────
        proposal: DesignProposal | None = state.get("proposal")
        if proposal is not None:
            proposal.required_actions = required_actions

        # ── enrich final_output if present ────────────────────────────────────
        final_output: dict | None = state.get("final_output")
        if final_output is not None:
            final_output = {
                **final_output,
                "required_actions": required_actions.model_dump(),
            }

        result = {**state}
        if final_output is not None:
            result["final_output"] = final_output

        return result
