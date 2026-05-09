from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.enums import VetoGateResult, VetoGateType
from isa_cad.core.models.reviewer import SecurityReviewerOutput
from isa_cad.core.models.veto import VetoGate


# ── Thresholds ────────────────────────────────────────────────────────────────

# Security score below which compliance gate blocks regardless of other signals
_SCORE_BLOCK_THRESHOLD   = 0.25
_SCORE_DEGRADE_THRESHOLD = 0.55


def evaluate_compliance_gate(review: SecurityReviewerOutput) -> VetoGate:
    """
    Pure function — evaluates the compliance veto gate from a
    SecurityReviewerOutput and returns a VetoGate.

    The compliance gate is distinct from the security gate:
      • Security gate   → structural posture (topology, IAM, exposure)
      • Compliance gate → regulatory obligations (PII, data residency,
                          compliance status, trust boundary legality)

    BLOCKED (G_j = 0.0) when ANY of:
        • pii_flow_status == "fail"  (PII accessible without auth)
        • data_residency_status == "fail"  (hard residency violation)
        • compliance_status == "fail"
        • trust_boundary_violations non-empty AND pii_flow_status != "pass"
          (boundary breach + uncertain PII → regulatory risk)
        • score < 0.25

    DEGRADED (G_j = 0.5) when ANY of (and not already BLOCKED):
        • data_residency_status == "warning"  (cross-region data store)
        • pii_flow_status == "unknown"  (PII handling not declared)
        • compliance_status == "warning"
        • trust_boundary_violations non-empty  (boundary breach alone)
        • score < 0.55

    PASSED (G_j = 1.0) otherwise.
    """
    pii_status    = review.pii_flow_status
    residency     = review.data_residency_status
    compliance    = review.compliance_status
    violations    = review.trust_boundary_violations
    score         = review.score

    # ── BLOCKED ───────────────────────────────────────────────────────────────
    block_reasons: list[str] = []

    if pii_status == "fail":
        block_reasons.append(
            "PII data is reachable from a public-facing component without "
            "authentication — violates GDPR Art. 32 / SOC2 CC6."
        )

    if residency == "fail":
        block_reasons.append(
            "Hard data residency violation detected — data store access "
            "crosses a restricted regional boundary."
        )

    if compliance == "fail":
        block_reasons.append(
            "Compliance status 'fail' — proposal does not satisfy minimum "
            "regulatory requirements."
        )

    if violations and pii_status not in ("pass",):
        block_reasons.append(
            f"{len(violations)} trust boundary violation(s) combined with "
            f"uncertain PII status ('{pii_status}') — unacceptable regulatory risk."
        )

    if score < _SCORE_BLOCK_THRESHOLD:
        block_reasons.append(
            f"Security/compliance score {score:.2f} is below the compliance "
            f"block threshold ({_SCORE_BLOCK_THRESHOLD})."
        )

    # Deduplicate (violations+pii may overlap with pii_status=="fail" reason)
    seen: set[str] = set()
    unique_block: list[str] = []
    for r in block_reasons:
        if r not in seen:
            seen.add(r)
            unique_block.append(r)

    if unique_block:
        return VetoGate(
            gate_type=VetoGateType.COMPLIANCE,
            result=VetoGateResult.BLOCKED,
            reason="Compliance gate BLOCKED: " + " | ".join(unique_block),
            required_action=(
                "Resolve all compliance violations before this proposal can proceed. "
                "Ensure PII data flows through an authenticated service layer, "
                "confirm data residency requirements are met, "
                "and obtain a DPO / compliance officer sign-off."
            ),
        )

    # ── DEGRADED ──────────────────────────────────────────────────────────────
    degrade_reasons: list[str] = []

    if residency == "warning":
        degrade_reasons.append(
            "Cross-region data store access detected — may require review "
            "under GDPR / data sovereignty regulations."
        )

    if pii_status == "unknown":
        degrade_reasons.append(
            "PII handling is not declared in node metadata. "
            "Regulatory impact cannot be fully assessed."
        )

    if compliance == "warning":
        degrade_reasons.append(
            "Compliance status 'warning' — some requirements need manual review."
        )

    if violations:
        degrade_reasons.append(
            f"{len(violations)} trust boundary violation(s) detected — "
            "potential legal exposure depending on data classification."
        )

    if score < _SCORE_DEGRADE_THRESHOLD:
        degrade_reasons.append(
            f"Security/compliance score {score:.2f} is below the compliance "
            f"degrade threshold ({_SCORE_DEGRADE_THRESHOLD})."
        )

    if degrade_reasons:
        return VetoGate(
            gate_type=VetoGateType.COMPLIANCE,
            result=VetoGateResult.DEGRADED,
            reason="Compliance gate DEGRADED (G_j=0.5): " + " | ".join(degrade_reasons),
            required_action=(
                "Compliance review required before production deploy. "
                "Declare PII handling in node metadata, confirm data residency "
                "alignment, and have a compliance officer review the proposal."
            ),
        )

    # ── PASSED ────────────────────────────────────────────────────────────────
    return VetoGate(
        gate_type=VetoGateType.COMPLIANCE,
        result=VetoGateResult.PASSED,
        reason=(
            f"Compliance gate PASSED (score={score:.2f}). "
            f"PII status: {pii_status}, residency: {residency}, "
            f"compliance: {compliance}. No regulatory violations detected."
        ),
        required_action=None,
    )


class ComplianceVetoGate:
    """
    LangGraph node — evaluates the compliance veto gate.

    Reads:   state["security_review"]   (contains pii, residency, compliance)
    Writes:  state["compliance_gate"]   (VetoGate)

    Distinct from SecurityVetoGate:
        • Security gate focuses on structural posture (topology, IAM, exposure)
        • Compliance gate focuses on regulatory obligations (GDPR, data
          residency, PII flow legality, trust boundary legality)
    """

    def __call__(self, state: AgentState) -> AgentState:
        review: SecurityReviewerOutput | None = state.get("security_review")

        if review is None:
            gate = VetoGate(
                gate_type=VetoGateType.COMPLIANCE,
                result=VetoGateResult.DEGRADED,
                reason="Compliance gate DEGRADED: no security_review in state.",
                required_action="Run SecurityReviewerNode before ComplianceVetoGate.",
            )
        else:
            gate = evaluate_compliance_gate(review)

        return {"compliance_gate": gate}
