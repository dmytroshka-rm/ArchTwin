from __future__ import annotations

from pydantic import Field

from .base import ISABaseModel, SimulationFidelity
from .blast_radius import BlastRadiusOutput
from .calibration import CalibrationResult
from .enums import ComparisonMode, OptimizationGoal, ProposalStatus
from .reviewer import CostReviewerOutput, PerformanceReviewerOutput, SecurityReviewerOutput
from .veto import VetoGateSet


class OptimizationWeights(ISABaseModel):
    """
    Weights for non-linear recommendation score based on optimization_goal.
    Section 3.1 — w_i values per goal.
    """
    cost: float = Field(0.25, ge=0.0, le=1.0)
    performance: float = Field(0.25, ge=0.0, le=1.0)
    reliability: float = Field(0.25, ge=0.0, le=1.0)
    security: float = Field(0.25, ge=0.0, le=1.0)

    @classmethod
    def from_goal(cls, goal: OptimizationGoal) -> "OptimizationWeights":
        presets: dict[OptimizationGoal, dict[str, float]] = {
            OptimizationGoal.COST_EFFICIENCY: {
                "cost": 0.45, "performance": 0.20, "reliability": 0.15, "security": 0.20
            },
            OptimizationGoal.MAX_RELIABILITY: {
                "cost": 0.10, "performance": 0.25, "reliability": 0.45, "security": 0.20
            },
            OptimizationGoal.MINIMAL_COMPLEXITY: {
                "cost": 0.20, "performance": 0.20, "reliability": 0.30, "security": 0.30
            },
            OptimizationGoal.BALANCED: {
                "cost": 0.25, "performance": 0.25, "reliability": 0.25, "security": 0.25
            },
        }
        return cls(**presets[goal])


class RequiredActions(ISABaseModel):
    """Persona-based required actions. Section 11.3."""
    developer: list[str] = Field(default_factory=list)
    architect: list[str] = Field(default_factory=list)
    security_ops: list[str] = Field(default_factory=list)
    data_fidelity: list[str] = Field(default_factory=list)


class NonLinearScoring(ISABaseModel):
    """Result of the non-linear recommendation score calculation."""
    recommendation_score: float = Field(0.0, ge=0.0, le=1.0)
    optimization_weights: OptimizationWeights = Field(default_factory=OptimizationWeights)
    veto_gates: VetoGateSet = Field(default_factory=VetoGateSet)
    raw_weighted_sum: float = Field(0.0, description="SUM_i(w_i * gain_i) before veto product")


class DesignProposal(ISABaseModel):
    """
    Full design proposal with sandbox layers, simulation, scoring and blast radius.
    Maps to isa.yaml design_proposals[] entry — Section 10.
    """
    id: str = Field(..., description="e.g. 'proposal.layer-a-serverless'")
    title: str
    status: ProposalStatus = Field(ProposalStatus.SANDBOX_LAYER)
    optimization_goal: OptimizationGoal = Field(OptimizationGoal.BALANCED)
    canvas_session_id: str | None = None

    # Comparison
    baseline_ref: str = Field(..., description="e.g. 'architecture.baseline.prod'")
    compare_against: list[str] = Field(default_factory=list)
    differential_mode: ComparisonMode = Field(ComparisonMode.BASELINE_TO_LAYER)

    # Fidelity
    simulation_fidelity: SimulationFidelity | None = None

    # Calibration
    calibration: CalibrationResult = Field(default_factory=CalibrationResult)

    # Scoring
    scoring: NonLinearScoring = Field(default_factory=NonLinearScoring)

    # Reviewer outputs
    cost_review: CostReviewerOutput | None = None
    performance_review: PerformanceReviewerOutput | None = None
    security_review: SecurityReviewerOutput | None = None

    # Blast radius
    blast_radius: BlastRadiusOutput | None = None

    # Actions
    required_actions: RequiredActions = Field(default_factory=RequiredActions)

    # Checkpoint
    checkpoint_id: str | None = None
    resume_node: str | None = None

    @property
    def is_blocked(self) -> bool:
        return (
            self.status == ProposalStatus.BLOCKED
            or self.scoring.veto_gates.is_blocked
        )
