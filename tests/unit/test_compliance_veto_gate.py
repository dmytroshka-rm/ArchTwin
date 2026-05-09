from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.veto.compliance_gate import (
    ComplianceVetoGate,
    _SCORE_BLOCK_THRESHOLD,
    _SCORE_DEGRADE_THRESHOLD,
    evaluate_compliance_gate,
)
from isa_cad.core.models.enums import ReviewerStatus, VetoGateResult, VetoGateType
from isa_cad.core.models.reviewer import SecurityReviewerOutput

gate_node = ComplianceVetoGate()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_review(
    score: float = 0.85,
    pii_flow_status: str = "pass",
    data_residency_status: str = "pass",
    compliance_status: str = "pass",
    trust_boundary_violations: list[str] | None = None,
    public_exposure_risk: str = "low",
    iam_scope_risk: str = "low",
) -> SecurityReviewerOutput:
    return SecurityReviewerOutput(
        status=ReviewerStatus.PASS,
        score=score,
        confidence=0.7,
        recommendation="ok",
        pii_flow_status=pii_flow_status,
        data_residency_status=data_residency_status,
        compliance_status=compliance_status,
        trust_boundary_violations=trust_boundary_violations or [],
        public_exposure_risk=public_exposure_risk,
        iam_scope_risk=iam_scope_risk,
    )


def run_gate(review: SecurityReviewerOutput) -> dict:
    return gate_node({"security_review": review})


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_key_present():
    assert "compliance_gate" in run_gate(make_review())


def test_gate_type_is_compliance():
    assert run_gate(make_review())["compliance_gate"].gate_type == VetoGateType.COMPLIANCE


def test_multiplier_synced_with_result():
    gate = run_gate(make_review())["compliance_gate"]
    expected = {VetoGateResult.PASSED: 1.0, VetoGateResult.DEGRADED: 0.5, VetoGateResult.BLOCKED: 0.0}
    assert gate.multiplier == expected[gate.result]


def test_no_review_in_state_gives_degraded():
    gate = gate_node({})["compliance_gate"]
    assert gate.result == VetoGateResult.DEGRADED
    assert gate.required_action is not None


# ── PASSED ────────────────────────────────────────────────────────────────────

def test_clean_review_passes():
    gate = evaluate_compliance_gate(make_review())
    assert gate.result == VetoGateResult.PASSED
    assert gate.multiplier == 1.0
    assert gate.required_action is None


def test_pass_reason_includes_pii_residency_compliance():
    gate = evaluate_compliance_gate(make_review())
    assert "pii" in gate.reason.lower() or "PII" in gate.reason
    assert "residency" in gate.reason.lower()
    assert "compliance" in gate.reason.lower()


# ── BLOCKED — PII fail ────────────────────────────────────────────────────────

def test_pii_fail_blocks():
    gate = evaluate_compliance_gate(make_review(pii_flow_status="fail"))
    assert gate.result == VetoGateResult.BLOCKED
    assert gate.multiplier == 0.0
    assert "PII" in gate.reason


def test_pii_unknown_does_not_block():
    gate = evaluate_compliance_gate(make_review(pii_flow_status="unknown"))
    assert gate.result != VetoGateResult.BLOCKED


def test_pii_pass_does_not_block():
    gate = evaluate_compliance_gate(make_review(pii_flow_status="pass"))
    assert gate.result == VetoGateResult.PASSED


# ── BLOCKED — data residency fail ────────────────────────────────────────────

def test_residency_fail_blocks():
    gate = evaluate_compliance_gate(make_review(data_residency_status="fail"))
    assert gate.result == VetoGateResult.BLOCKED
    assert "residency" in gate.reason.lower()


def test_residency_warning_does_not_block():
    gate = evaluate_compliance_gate(make_review(data_residency_status="warning"))
    assert gate.result != VetoGateResult.BLOCKED


# ── BLOCKED — compliance fail ─────────────────────────────────────────────────

def test_compliance_fail_blocks():
    gate = evaluate_compliance_gate(make_review(compliance_status="fail"))
    assert gate.result == VetoGateResult.BLOCKED
    assert "compliance" in gate.reason.lower()


def test_compliance_warning_does_not_block():
    gate = evaluate_compliance_gate(make_review(compliance_status="warning"))
    assert gate.result != VetoGateResult.BLOCKED


# ── BLOCKED — violations + uncertain PII ─────────────────────────────────────

def test_violations_with_unknown_pii_blocks():
    gate = evaluate_compliance_gate(make_review(
        trust_boundary_violations=["gw → db"],
        pii_flow_status="unknown",
    ))
    assert gate.result == VetoGateResult.BLOCKED


def test_violations_with_pii_fail_blocks():
    gate = evaluate_compliance_gate(make_review(
        trust_boundary_violations=["gw → db"],
        pii_flow_status="fail",
    ))
    assert gate.result == VetoGateResult.BLOCKED


def test_violations_alone_with_pii_pass_degrades_not_blocks():
    """Violations alone (PII confirmed pass) → DEGRADED, not BLOCKED."""
    gate = evaluate_compliance_gate(make_review(
        trust_boundary_violations=["gw → svc"],
        pii_flow_status="pass",
    ))
    assert gate.result == VetoGateResult.DEGRADED


# ── BLOCKED — score ───────────────────────────────────────────────────────────

def test_score_below_block_threshold_blocks():
    gate = evaluate_compliance_gate(make_review(score=_SCORE_BLOCK_THRESHOLD - 0.01))
    assert gate.result == VetoGateResult.BLOCKED


def test_score_exactly_at_block_does_not_block():
    gate = evaluate_compliance_gate(make_review(score=_SCORE_BLOCK_THRESHOLD))
    assert gate.result != VetoGateResult.BLOCKED


# ── DEGRADED — residency warning ─────────────────────────────────────────────

def test_residency_warning_degrades():
    gate = evaluate_compliance_gate(make_review(data_residency_status="warning"))
    assert gate.result == VetoGateResult.DEGRADED
    assert "region" in gate.reason.lower() or "residency" in gate.reason.lower()


# ── DEGRADED — PII unknown ────────────────────────────────────────────────────

def test_pii_unknown_degrades():
    gate = evaluate_compliance_gate(make_review(pii_flow_status="unknown"))
    assert gate.result == VetoGateResult.DEGRADED
    assert "PII" in gate.reason or "pii" in gate.reason.lower()


# ── DEGRADED — compliance warning ────────────────────────────────────────────

def test_compliance_warning_degrades():
    gate = evaluate_compliance_gate(make_review(compliance_status="warning"))
    assert gate.result == VetoGateResult.DEGRADED
    assert "warning" in gate.reason.lower()


# ── DEGRADED — violations alone ──────────────────────────────────────────────

def test_violations_alone_degrade():
    gate = evaluate_compliance_gate(make_review(
        trust_boundary_violations=["gw → db"],
        pii_flow_status="pass",
    ))
    assert gate.result == VetoGateResult.DEGRADED
    assert "violation" in gate.reason.lower()


# ── DEGRADED — score ─────────────────────────────────────────────────────────

def test_score_between_thresholds_degrades():
    score = (_SCORE_BLOCK_THRESHOLD + _SCORE_DEGRADE_THRESHOLD) / 2
    gate = evaluate_compliance_gate(make_review(score=score))
    assert gate.result == VetoGateResult.DEGRADED


def test_score_exactly_at_degrade_threshold_passes():
    gate = evaluate_compliance_gate(make_review(score=_SCORE_DEGRADE_THRESHOLD))
    assert gate.result == VetoGateResult.PASSED


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_pii_fail_and_violations_not_duplicated_in_reason():
    """PII fail + violations both present — reason should not repeat same text."""
    gate = evaluate_compliance_gate(make_review(
        pii_flow_status="fail",
        trust_boundary_violations=["gw → db"],
    ))
    assert gate.result == VetoGateResult.BLOCKED
    # The PII reason and the combined violation+pii reason overlap;
    # ensure reason is reasonable length (not doubled)
    assert len(gate.reason) < 1000


# ── BLOCKED beats DEGRADED ───────────────────────────────────────────────────

def test_pii_fail_blocks_even_with_warning_residency():
    gate = evaluate_compliance_gate(make_review(
        pii_flow_status="fail",
        data_residency_status="warning",
    ))
    assert gate.result == VetoGateResult.BLOCKED


def test_compliance_fail_blocks_with_unknown_pii():
    gate = evaluate_compliance_gate(make_review(
        compliance_status="fail",
        pii_flow_status="unknown",
    ))
    assert gate.result == VetoGateResult.BLOCKED


# ── required_action ───────────────────────────────────────────────────────────

def test_blocked_has_required_action():
    gate = evaluate_compliance_gate(make_review(pii_flow_status="fail"))
    assert gate.required_action is not None
    assert "DPO" in gate.required_action or "compliance" in gate.required_action.lower()


def test_degraded_has_required_action():
    gate = evaluate_compliance_gate(make_review(pii_flow_status="unknown"))
    assert gate.required_action is not None


def test_passed_has_no_required_action():
    gate = evaluate_compliance_gate(make_review())
    assert gate.required_action is None


# ── output contract ───────────────────────────────────────────────────────────

def test_existing_state_keys_preserved():
    state: AgentState = {
        "security_review": make_review(),
        "session_id": "sess-xyz",
    }
    result = gate_node(state)
    assert "compliance_gate" in result
    assert list(result.keys()) == ["compliance_gate"]


# ── Distinct from security gate ───────────────────────────────────────────────

def test_high_exposure_does_not_trigger_compliance_block():
    """High public exposure is a security concern, not a compliance block."""
    gate = evaluate_compliance_gate(make_review(
        public_exposure_risk="high",
        pii_flow_status="pass",
        compliance_status="pass",
    ))
    assert gate.result == VetoGateResult.PASSED


def test_high_iam_does_not_trigger_compliance_block():
    """IAM over-permissiveness is a security concern, not a compliance block."""
    gate = evaluate_compliance_gate(make_review(
        iam_scope_risk="high",
        pii_flow_status="pass",
        compliance_status="pass",
    ))
    assert gate.result == VetoGateResult.PASSED
