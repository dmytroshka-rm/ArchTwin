from __future__ import annotations

from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.logging import get_logger
from isa_cad.core.models.enums import HumanDecision, ProposalStatus, VetoGateResult

_log = get_logger(__name__)
from isa_cad.core.models.human_review import HumanReviewRequest
from isa_cad.core.models.proposal import DesignProposal
from isa_cad.core.models.veto import VetoGate

# Blast-radius high-risk threshold above which a human must review
_HIGH_RISK_THRESHOLD = 2


# ── HumanReviewGateNode ───────────────────────────────────────────────────────

def _build_review_request(state: AgentState) -> HumanReviewRequest:
    """
    Evaluate all escalation signals and build a HumanReviewRequest.

    Priority (highest wins for escalation_level):
        critical  — proposal is BLOCKED
        warning   — calibration human_review flag, or ≥2 high-risk blast components
        info      — decision is CANDIDATE_FOR_REVIEW, or fidelity data is stale

    Available decisions:
        Always offered: APPROVE_SANDBOX_LAYER, BLOCK_PROPOSAL, MODIFY_GOAL
        + REQUEST_REFRESH  when fidelity gate is non-passing
        + ACCEPT_RISK_WITH_ADR  when non-critical risks remain (not hard-blocked)
    """
    reasons: list[str] = []
    level = "info"
    options: set[HumanDecision] = {
        HumanDecision.APPROVE_SANDBOX_LAYER,
        HumanDecision.BLOCK_PROPOSAL,
        HumanDecision.MODIFY_GOAL,
    }

    # ── Signal: proposal BLOCKED ──────────────────────────────────────────────
    is_blocked: bool = state.get("is_blocked", False)
    if is_blocked:
        level = "critical"
        block_reasons: list[str] = state.get("block_reasons") or []
        reasons.append("Proposal is BLOCKED. Review block reasons before proceeding.")
        if block_reasons:
            reasons.extend(block_reasons)

    # ── Signal: calibration human_review_required ─────────────────────────────
    cal = state.get("calibration_loop_output")
    if cal and cal.human_review_required:
        if level != "critical":
            level = "warning"
        reasons.append(
            "Security false negative detected in calibration history. "
            "Manual security validation required before approval."
        )

    # ── Signal: blast radius high-risk count ──────────────────────────────────
    br = state.get("blast_radius")
    if br and br.high_risk_count >= _HIGH_RISK_THRESHOLD:
        if level != "critical":
            level = "warning"
        reasons.append(
            f"{br.high_risk_count} high-risk Tier-1 components in blast radius. "
            "Architect sign-off required."
        )

    # ── Signal: fidelity gate non-passing → offer REQUEST_REFRESH ────────────
    fidelity_gate: VetoGate | None = state.get("fidelity_gate")
    if fidelity_gate and fidelity_gate.result != VetoGateResult.PASSED:
        options.add(HumanDecision.REQUEST_REFRESH)
        reasons.append(
            f"Fidelity gate is {fidelity_gate.result.value}. "
            "A data refresh would upgrade output_mode to FINAL_FORECAST."
        )

    # ── Signal: decision is CANDIDATE_FOR_REVIEW ──────────────────────────────
    fo: dict | None = state.get("final_output")
    if fo and fo.get("decision") == ProposalStatus.CANDIDATE_FOR_REVIEW.value:
        if not reasons:
            reasons.append(
                "Proposal scored below the approval threshold. "
                "Human review required before promotion."
            )

    # ── ACCEPT_RISK_WITH_ADR: available for non-critical cases ───────────────
    if level != "critical" and reasons:
        options.add(HumanDecision.ACCEPT_RISK_WITH_ADR)

    required = bool(reasons)

    deadline_hint = ""
    if fidelity_gate and fidelity_gate.result != VetoGateResult.PASSED:
        deadline_hint = "Refresh observed graph before treating output as a Final Forecast."

    return HumanReviewRequest(
        required=required,
        reasons=reasons,
        escalation_level=level if required else "info",
        options=sorted(options, key=lambda d: d.value),
        deadline_hint=deadline_hint,
    )


class HumanReviewGateNode:
    """
    LangGraph node — evaluates escalation signals and emits a HumanReviewRequest.
    Section 8.1 — Human-in-the-Loop & Safety.

    When human_review_request.required is True this node also sets
    checkpoint_required=True so the pipeline checkpoints before waiting.

    Reads:
        state["is_blocked"]               bool
        state["block_reasons"]            list[str]
        state["calibration_loop_output"]  CalibrationLoopOutput
        state["blast_radius"]             BlastRadiusOutput
        state["fidelity_gate"]            VetoGate
        state["final_output"]             dict (checks decision value)

    Writes:
        state["human_review_request"]  dict (serialised HumanReviewRequest)
        state["checkpoint_required"]   True when review is required (else unchanged)
    """

    def __call__(self, state: AgentState) -> AgentState:
        request = _build_review_request(state)
        if request.required:
            _log.warning(
                "human_review.required",
                escalation_level=request.escalation_level,
                reason_count=len(request.reasons),
                options=request.options,
            )
        else:
            _log.info("human_review.not_required")
        result = {**state, "human_review_request": request.model_dump()}
        if request.required:
            result["checkpoint_required"] = True
        return result


# ── HumanDecisionProcessorNode ────────────────────────────────────────────────

def _apply_approve(state: AgentState, result: dict) -> None:
    proposal: DesignProposal | None = state.get("proposal")
    if proposal is not None:
        proposal.status = ProposalStatus.APPROVED
    fo: dict | None = result.get("final_output")
    if fo is not None:
        result["final_output"] = {**fo, "decision": ProposalStatus.APPROVED.value}


def _apply_block(state: AgentState, result: dict) -> None:
    proposal: DesignProposal | None = state.get("proposal")
    if proposal is not None:
        proposal.status = ProposalStatus.BLOCKED
    result["is_blocked"] = True
    existing = list(result.get("block_reasons") or [])
    msg = "[human_decision] Proposal blocked by human reviewer."
    if msg not in existing:
        existing.append(msg)
    result["block_reasons"] = existing
    fo: dict | None = result.get("final_output")
    if fo is not None:
        result["final_output"] = {
            **fo,
            "decision": ProposalStatus.BLOCKED.value,
            "is_blocked": True,
            "block_reasons": existing,
        }


def _apply_request_refresh(state: AgentState, result: dict) -> None:
    session = state.get("canvas_session")
    if session is not None:
        session.mark_stale()
    result["checkpoint_required"] = True


def _apply_accept_risk_with_adr(state: AgentState, result: dict) -> None:
    proposal: DesignProposal | None = state.get("proposal")
    if proposal is not None:
        proposal.status = ProposalStatus.APPROVED
        adr_note = (
            "RISK ACCEPTED WITH ADR: Human reviewer approved this proposal with "
            "acknowledged risk. An Architecture Decision Record must be filed."
        )
        existing = list(proposal.required_actions.architect)
        if adr_note not in existing:
            existing.append(adr_note)
        proposal.required_actions.architect = existing
    fo: dict | None = result.get("final_output")
    if fo is not None:
        result["final_output"] = {**fo, "decision": ProposalStatus.APPROVED.value,
                                  "adr_required": True}


def _apply_modify_goal(state: AgentState, result: dict) -> None:
    """
    Signal the caller that a goal change is needed.
    The new goal is not set here — caller must provide it in the next run.
    """
    result["needs_rerun"] = True
    fo: dict | None = result.get("final_output")
    if fo is not None:
        result["final_output"] = {**fo, "needs_rerun": True,
                                  "rerun_reason": "Human requested optimization_goal change."}


_DECISION_HANDLERS = {
    HumanDecision.APPROVE_SANDBOX_LAYER:  _apply_approve,
    HumanDecision.BLOCK_PROPOSAL:         _apply_block,
    HumanDecision.REQUEST_REFRESH:        _apply_request_refresh,
    HumanDecision.ACCEPT_RISK_WITH_ADR:   _apply_accept_risk_with_adr,
    HumanDecision.MODIFY_GOAL:            _apply_modify_goal,
}


class HumanDecisionProcessorNode:
    """
    LangGraph node — applies a human decision to the current pipeline state.
    Section 8.2 — Human-in-the-Loop & Safety.

    Decision effects:
        APPROVE_SANDBOX_LAYER  → proposal.status = APPROVED
        BLOCK_PROPOSAL         → proposal.status = BLOCKED, is_blocked = True
        REQUEST_REFRESH        → session.mark_stale(), checkpoint_required = True
        ACCEPT_RISK_WITH_ADR   → proposal.status = APPROVED + ADR note in required_actions
        MODIFY_GOAL            → needs_rerun = True (caller re-runs with new goal)

    No-op when state["human_decision"] is absent.

    Reads:
        state["human_decision"]   HumanDecision (provided by external caller)
        state["proposal"]         DesignProposal (mutated in-place)
        state["canvas_session"]   CanvasSessionState (for REQUEST_REFRESH)
        state["final_output"]     dict (enriched with decision result)

    Writes:
        state["proposal"].status  (updated)
        state["is_blocked"]       (updated for BLOCK)
        state["block_reasons"]    (appended for BLOCK)
        state["checkpoint_required"] (set True for REQUEST_REFRESH)
        state["needs_rerun"]      (set True for MODIFY_GOAL)
        state["final_output"]     (enriched)
    """

    def __call__(self, state: AgentState) -> AgentState:
        decision: HumanDecision | None = state.get("human_decision")
        if decision is None:
            _log.debug("human_decision.absent")
            return {**state}
        _log.info("human_decision.applied", decision=decision.value)

        result = {**state}
        handler = _DECISION_HANDLERS.get(decision)
        if handler is not None:
            handler(state, result)

        return result
