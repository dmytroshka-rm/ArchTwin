from __future__ import annotations

import pytest

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.veto.security_gate import (
    SecurityVetoGate,
    _SCORE_BLOCK_THRESHOLD,
    _SCORE_DEGRADE_THRESHOLD,
    evaluate_security_gate,
)
from isa_cad.core.models.enums import ReviewerStatus, VetoGateResult, VetoGateType
from isa_cad.core.models.reviewer import SecurityReviewerOutput

gate_node = SecurityVetoGate()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_review(
    score: float = 0.9,
    compliance_status: str = "pass",
    pii_flow_status: str = "pass",
    trust_boundary_violations: list[str] | None = None,
    public_exposure_risk: str = "low",
    iam_scope_risk: str = "low",
    status: ReviewerStatus = ReviewerStatus.PASS,
) -> SecurityReviewerOutput:
    return SecurityReviewerOutput(
        status=status,
        score=score,
        confidence=0.7,
        recommendation="ok",
        compliance_status=compliance_status,
        pii_flow_status=pii_flow_status,
        trust_boundary_violations=trust_boundary_violations or [],
        public_exposure_risk=public_exposure_risk,
        iam_scope_risk=iam_scope_risk,
    )


def run_gate(review: SecurityReviewerOutput) -> dict:
    state: AgentState = {"security_review": review}
    return gate_node(state)


# ── Output contract ───────────────────────────────────────────────────────────

def test_output_key_present():
    result = run_gate(make_review())
    assert "security_gate" in result


def test_gate_type_is_security():
    result = run_gate(make_review())
    assert result["security_gate"].gate_type == VetoGateType.SECURITY


def test_multiplier_synced_with_result():
    """model_post_init must keep multiplier consistent with result."""
    gate = run_gate(make_review())["security_gate"]
    expected = {
        VetoGateResult.PASSED:   1.0,
        VetoGateResult.DEGRADED: 0.5,
        VetoGateResult.BLOCKED:  0.0,
    }
    assert gate.multiplier == expected[gate.result]


def test_no_review_in_state_gives_degraded():
    result = gate_node({})
    gate = result["security_gate"]
    assert gate.result == VetoGateResult.DEGRADED
    assert gate.required_action is not None


# ── PASSED ────────────────────────────────────────────────────────────────────

def test_clean_review_passes():
    gate = evaluate_security_gate(make_review(score=0.95))
    assert gate.result == VetoGateResult.PASSED
    assert gate.multiplier == 1.0
    assert gate.required_action is None


def test_pass_reason_contains_score():
    gate = evaluate_security_gate(make_review(score=0.88))
    assert "0.88" in gate.reason


# ── BLOCKED — trust violations ────────────────────────────────────────────────

def test_trust_violation_blocks():
    review = make_review(trust_boundary_violations=["gw → db: public to data store"])
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.BLOCKED
    assert gate.multiplier == 0.0


def test_multiple_violations_all_in_reason():
    violations = ["v1", "v2", "v3"]
    review = make_review(trust_boundary_violations=violations)
    gate = evaluate_security_gate(review)
    assert "3" in gate.reason
    assert gate.result == VetoGateResult.BLOCKED


def test_many_violations_reason_truncated():
    """More than 2 violations should not dump all into reason (use '...')."""
    violations = [f"violation_{i}" for i in range(5)]
    review = make_review(trust_boundary_violations=violations)
    gate = evaluate_security_gate(review)
    assert "..." in gate.reason


# ── BLOCKED — PII fail ────────────────────────────────────────────────────────

def test_pii_fail_blocks():
    review = make_review(pii_flow_status="fail", score=0.7)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.BLOCKED
    assert "PII" in gate.reason


def test_pii_unknown_does_not_block():
    review = make_review(pii_flow_status="unknown", score=0.75)
    gate = evaluate_security_gate(review)
    assert gate.result != VetoGateResult.BLOCKED


# ── BLOCKED — compliance fail ─────────────────────────────────────────────────

def test_compliance_fail_blocks():
    review = make_review(compliance_status="fail", score=0.7)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.BLOCKED
    assert "compliance" in gate.reason.lower()


def test_compliance_warning_does_not_block():
    review = make_review(compliance_status="warning", score=0.75)
    gate = evaluate_security_gate(review)
    # warning → may degrade but not block
    assert gate.result != VetoGateResult.BLOCKED


# ── BLOCKED — low score ───────────────────────────────────────────────────────

def test_score_below_block_threshold_blocks():
    review = make_review(score=_SCORE_BLOCK_THRESHOLD - 0.01)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.BLOCKED


def test_score_exactly_at_block_threshold_does_not_block():
    review = make_review(score=_SCORE_BLOCK_THRESHOLD)
    gate = evaluate_security_gate(review)
    assert gate.result != VetoGateResult.BLOCKED


# ── DEGRADED — high exposure ──────────────────────────────────────────────────

def test_high_exposure_degrades():
    review = make_review(public_exposure_risk="high", score=0.70)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.DEGRADED
    assert gate.multiplier == 0.5


def test_medium_exposure_passes():
    review = make_review(public_exposure_risk="medium", score=0.85)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.PASSED


# ── DEGRADED — high IAM risk ──────────────────────────────────────────────────

def test_high_iam_risk_degrades():
    review = make_review(iam_scope_risk="high", score=0.70)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.DEGRADED
    assert "IAM" in gate.reason


def test_medium_iam_risk_passes():
    review = make_review(iam_scope_risk="medium", score=0.85)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.PASSED


# ── DEGRADED — score below degrade threshold ──────────────────────────────────

def test_score_below_degrade_threshold_degrades():
    # Above block, below degrade
    score = (_SCORE_BLOCK_THRESHOLD + _SCORE_DEGRADE_THRESHOLD) / 2
    review = make_review(score=score)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.DEGRADED


def test_score_exactly_at_degrade_threshold_passes():
    review = make_review(score=_SCORE_DEGRADE_THRESHOLD)
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.PASSED


# ── BLOCKED wins over DEGRADED ────────────────────────────────────────────────

def test_violation_blocks_even_when_score_would_only_degrade():
    """Trust violation → BLOCKED, not just DEGRADED, regardless of score."""
    score = (_SCORE_BLOCK_THRESHOLD + _SCORE_DEGRADE_THRESHOLD) / 2
    review = make_review(
        score=score,
        trust_boundary_violations=["gw → db"],
    )
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.BLOCKED


def test_pii_fail_blocks_even_with_good_score():
    review = make_review(score=0.80, pii_flow_status="fail")
    gate = evaluate_security_gate(review)
    assert gate.result == VetoGateResult.BLOCKED


# ── required_action ───────────────────────────────────────────────────────────

def test_blocked_has_required_action():
    review = make_review(trust_boundary_violations=["v1"])
    gate = evaluate_security_gate(review)
    assert gate.required_action is not None
    assert len(gate.required_action) > 0


def test_degraded_has_required_action():
    review = make_review(public_exposure_risk="high", score=0.70)
    gate = evaluate_security_gate(review)
    assert gate.required_action is not None


def test_passed_has_no_required_action():
    gate = evaluate_security_gate(make_review(score=0.95))
    assert gate.required_action is None


# ── output contract ───────────────────────────────────────────────────────────
# Parallel veto-gate nodes return only their own key so LangGraph can merge
# concurrent branches without conflicts.

def test_existing_state_keys_preserved():
    review = make_review()
    state: AgentState = {"security_review": review, "session_id": "test-123"}
    result = gate_node(state)
    # Node writes only security_gate — state passthrough is handled by LangGraph
    assert "security_gate" in result
    assert list(result.keys()) == ["security_gate"]
