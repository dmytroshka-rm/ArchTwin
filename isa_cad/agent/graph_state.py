from __future__ import annotations

from typing import Any, TypedDict

from isa_cad.core.freshness_engine import FreshnessReport
from isa_cad.core.math_models.calibration_loop import CalibrationLoopOutput
from isa_cad.core.models.calibration import CalibrationResult
from isa_cad.core.models.checkpoint import Checkpoint
from isa_cad.core.models.enums import HumanDecision, OptimizationGoal, OutputMode
from isa_cad.core.models.proposal import DesignProposal
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGate, VetoGateSet
from isa_cad.core.models.blast_radius import BlastRadiusOutput
from isa_cad.state.canvas_state import CanvasSessionState, ComponentGraph


class AgentState(TypedDict, total=False):
    """
    Central state object passed through every LangGraph node.
    Each node reads what it needs and writes its outputs back.
    Section 4 — LangGraph Workflow v0.5.3.
    """

    # ── input: provided by caller before graph starts ────────────────────────
    session_id: str
    proposal_id: str
    baseline_ref: str
    optimization_goal: OptimizationGoal

    # ── ContextAndFreshnessNode outputs ──────────────────────────────────────
    canvas_session: CanvasSessionState        # loaded or restored session
    resolved_graph: ComponentGraph            # baseline + active sandbox layers
    freshness_report: FreshnessReport         # data age analysis
    calibration_result: CalibrationResult     # historical error data
    context_ready: bool                       # True when node completed OK
    context_errors: list[str]                 # any warnings / missing data

    # ── BuildDesignDeltaNode outputs ─────────────────────────────────────────
    design_delta: dict[str, Any]              # added/removed/modified components
    source_component_id: str                  # component being modified

    # ── Parallel reviewer outputs ─────────────────────────────────────────────
    cost_review: CostReviewerOutput
    performance_review: PerformanceReviewerOutput
    security_review: SecurityReviewerOutput
    reviewer_summary: dict[str, Any]            # aggregated signals from ParallelReviewerNode

    # ── Individual veto gate outputs (4.1 – 4.4) ─────────────────────────────
    security_gate:    VetoGate
    reliability_gate: VetoGate
    compliance_gate:  VetoGate
    fidelity_gate:    VetoGate

    # ── TradeoffAndVetoGateNode outputs ──────────────────────────────────────
    proposal: DesignProposal                  # scored proposal with veto results

    # ── BlastRadiusNode outputs ───────────────────────────────────────────────
    blast_radius: BlastRadiusOutput
    blast_radius_diff: dict[str, Any]           # diff vs baseline blast radius (optional)

    # ── CalibrationAndBiasAdjustmentNode outputs ──────────────────────────────
    calibration_loop_output: CalibrationLoopOutput

    # ── StatePersistenceNode outputs ──────────────────────────────────────────
    checkpoint: Checkpoint | None
    checkpoint_required: bool

    # ── ReflectAndDecideNode outputs ──────────────────────────────────────────
    output_mode: OutputMode
    final_output: dict[str, Any]              # Decision-Grade Output Contract
    is_blocked: bool
    block_reasons: list[str]

    # ── IsaYamlPatchNode outputs ──────────────────────────────────────────────
    isa_yaml_patch: dict[str, Any]            # schema-valid proposal patch dict

    # ── SandboxRecommendationNode outputs ─────────────────────────────────────
    recommendations: list[dict[str, Any]]     # goal-aligned architecture recommendations

    # ── HumanReviewGateNode outputs ───────────────────────────────────────────
    human_review_request: dict[str, Any]      # HumanReviewRequest serialised

    # ── HumanDecisionProcessorNode inputs/outputs ─────────────────────────────
    human_decision: HumanDecision             # provided by external caller
    needs_rerun: bool                         # True when MODIFY_GOAL requires re-run
