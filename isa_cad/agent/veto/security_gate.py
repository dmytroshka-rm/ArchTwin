from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.enums import VetoGateResult, VetoGateType
from isa_cad.core.models.reviewer import SecurityReviewerOutput
from isa_cad.core.models.veto import VetoGate


# ── Thresholds ────────────────────────────────────────────────────────────────

# Any of these compliance statuses → BLOCKED immediately
_BLOCKING_COMPLIANCE = {"fail"}

# Security reviewer scores below this → BLOCKED
_SCORE_BLOCK_THRESHOLD = 0.30

# Security reviewer scores in this range → DEGRADED (G_j = 0.5)
_SCORE_DEGRADE_THRESHOLD = 0.60


def evaluate_security_gate(review: SecurityReviewerOutput) -> VetoGate:
    """
    Pure function — evaluates the security veto gate from a
    SecurityReviewerOutput and returns a VetoGate.

    BLOCKED (G_j = 0.0) when ANY of:
        • trust_boundary_violations is non-empty
        • pii_flow_status == "fail"
        • compliance_status == "fail"
        • score < 0.30

    DEGRADED (G_j = 0.5) when ANY of (and not already BLOCKED):
        • public_exposure_risk == "high"
        • iam_scope_risk == "high"
        • score < 0.60

    PASSED (G_j = 1.0) otherwise.
    """
    violations  = review.trust_boundary_violations
    pii_status  = review.pii_flow_status
    compliance  = review.compliance_status
    score       = review.score
    exposure    = review.public_exposure_risk or "low"
    iam_risk    = review.iam_scope_risk or "low"

    # ── BLOCKED ───────────────────────────────────────────────────────────────
    block_reasons: list[str] = []

    if violations:
        block_reasons.append(
            f"{len(violations)} trust boundary violation(s): "
            + "; ".join(violations[:2])
            + (" ..." if len(violations) > 2 else "")
        )

    if pii_status == "fail":
        block_reasons.append(
            "PII data is reachable from a public-facing component without "
            "passing through an authentication layer."
        )

    if compliance in _BLOCKING_COMPLIANCE:
        block_reasons.append(
            f"Compliance status is '{compliance}' — proposal does not meet "
            "minimum security compliance requirements."
        )

    if score < _SCORE_BLOCK_THRESHOLD:
        block_reasons.append(
            f"Security score {score:.2f} is below the block threshold "
            f"({_SCORE_BLOCK_THRESHOLD})."
        )

    if block_reasons:
        return VetoGate(
            gate_type=VetoGateType.SECURITY,
            result=VetoGateResult.BLOCKED,
            reason="Security gate BLOCKED: " + " | ".join(block_reasons),
            required_action=(
                "Remediate all trust boundary violations and PII exposure "
                "before this proposal can proceed. "
                "Insert auth layers, apply network segmentation, "
                "and re-run the security reviewer."
            ),
        )

    # ── DEGRADED ──────────────────────────────────────────────────────────────
    degrade_reasons: list[str] = []

    if exposure == "high":
        degrade_reasons.append(
            "High public exposure risk — data stores or Tier-1 resources are "
            "directly reachable from the internet."
        )

    if iam_risk == "high":
        degrade_reasons.append(
            "Over-permissive IAM scope — an IAM-bound resource is called by "
            "more than 4 distinct services."
        )

    if score < _SCORE_DEGRADE_THRESHOLD:
        degrade_reasons.append(
            f"Security score {score:.2f} is below the degrade threshold "
            f"({_SCORE_DEGRADE_THRESHOLD})."
        )

    if degrade_reasons:
        return VetoGate(
            gate_type=VetoGateType.SECURITY,
            result=VetoGateResult.DEGRADED,
            reason="Security gate DEGRADED (G_j=0.5): " + " | ".join(degrade_reasons),
            required_action=(
                "Address the flagged security concerns before production deploy. "
                "Human review required. Proposal may proceed to sandbox only."
            ),
        )

    # ── PASSED ────────────────────────────────────────────────────────────────
    return VetoGate(
        gate_type=VetoGateType.SECURITY,
        result=VetoGateResult.PASSED,
        reason=(
            f"Security gate PASSED (score={score:.2f}). "
            "No trust violations, PII exposure, or compliance failures detected."
        ),
        required_action=None,
    )


class SecurityVetoGate:
    """
    LangGraph node — evaluates the security veto gate.

    Reads:   state["security_review"]
    Writes:  state["security_gate"]  (VetoGate)

    The gate result is later consumed by TradeoffAndVetoGateNode which
    assembles the full VetoGateSet and applies PRODUCT(G_j) to the score.
    """

    def __call__(self, state: AgentState) -> AgentState:
        review: SecurityReviewerOutput | None = state.get("security_review")

        if review is None:
            gate = VetoGate(
                gate_type=VetoGateType.SECURITY,
                result=VetoGateResult.DEGRADED,
                reason="Security gate DEGRADED: no security_review in state.",
                required_action="Run SecurityReviewerNode before SecurityVetoGate.",
            )
        else:
            gate = evaluate_security_gate(review)

        return {"security_gate": gate}
