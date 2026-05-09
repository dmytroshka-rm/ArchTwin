from __future__ import annotations

from dataclasses import dataclass, field

from isa_cad.core.models.enums import OptimizationGoal, ReviewerStatus, ReviewerType
from isa_cad.core.models.proposal import NonLinearScoring, OptimizationWeights
from isa_cad.core.models.reviewer import (
    CostReviewerOutput,
    PerformanceReviewerOutput,
    ReviewerOutput,
    SecurityReviewerOutput,
)
from isa_cad.core.models.veto import VetoGateSet


@dataclass
class GainVector:
    """
    Normalized gain/degradation for each metric dimension.
    gain_i ∈ [-1.0, +1.0]:
        +1.0 = maximum improvement over baseline
         0.0 = no change
        -1.0 = maximum degradation

    Convention Section 3.1:
        gain_i = normalized improvement/degradation for
                 Cost, Performance, Reliability, Complexity
    """
    cost: float = 0.0         # positive = cheaper than baseline
    performance: float = 0.0  # positive = faster / lower latency
    reliability: float = 0.0  # positive = higher SLO
    security: float = 0.0     # positive = more secure
    complexity: float = 0.0   # positive = less complex (used for display, not in score)

    def clamp(self) -> "GainVector":
        """Return a new GainVector with all values clamped to [-1, 1]."""
        return GainVector(
            cost=max(-1.0, min(1.0, self.cost)),
            performance=max(-1.0, min(1.0, self.performance)),
            reliability=max(-1.0, min(1.0, self.reliability)),
            security=max(-1.0, min(1.0, self.security)),
            complexity=max(-1.0, min(1.0, self.complexity)),
        )


@dataclass
class ScoringInput:
    """All inputs required to compute the non-linear recommendation score."""
    gain_vector: GainVector
    veto_gates: VetoGateSet
    optimization_goal: OptimizationGoal = OptimizationGoal.BALANCED
    weights: OptimizationWeights | None = None   # override; derived from goal if None


@dataclass
class ScoringResult:
    """
    Full result of the non-linear recommendation score computation.

    Formula (Section 3.1):
        recommendation_score = SUM_i(w_i * gain_i) * PRODUCT_j(G_j)
    """
    recommendation_score: float       # final score ∈ [0, 1]
    raw_weighted_sum: float           # SUM_i(w_i * gain_i) before veto product
    veto_product: float               # PRODUCT_j(G_j)
    weights: OptimizationWeights
    gain_vector: GainVector
    veto_gates: VetoGateSet
    is_blocked: bool
    score_breakdown: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_non_linear_scoring(self) -> NonLinearScoring:
        return NonLinearScoring(
            recommendation_score=round(self.recommendation_score, 4),
            optimization_weights=self.weights,
            veto_gates=self.veto_gates,
            raw_weighted_sum=round(self.raw_weighted_sum, 4),
        )


class RecommendationScorer:
    """
    Computes the non-linear recommendation score.

    recommendation_score = (SUM_i(w_i * gain_i)) * PRODUCT_j(G_j)

    Key properties (Section 3.1):
      - Veto gate G_j = 0.0 collapses entire score to 0.0 (critical fail)
      - Veto gate G_j = 0.5 halves the score (degraded mode)
      - Veto gate G_j = 1.0 passes through unchanged
      - raw_weighted_sum is normalized to [0, 1] before applying veto product
    """

    def compute(self, inp: ScoringInput) -> ScoringResult:
        weights = inp.weights or OptimizationWeights.from_goal(inp.optimization_goal)
        gains = inp.gain_vector.clamp()

        # SUM_i(w_i * gain_i)  — can be negative if all metrics degrade
        weighted_terms = {
            "cost":        weights.cost        * gains.cost,
            "performance": weights.performance * gains.performance,
            "reliability": weights.reliability * gains.reliability,
            "security":    weights.security    * gains.security,
        }
        raw_sum = sum(weighted_terms.values())

        # Normalize raw_sum from [-1, 1] to [0, 1]
        # A proposal with no gain/degradation → 0.5 (neutral)
        normalized = (raw_sum + 1.0) / 2.0
        normalized = max(0.0, min(1.0, normalized))

        # PRODUCT_j(G_j)
        veto_product = inp.veto_gates.product

        # Final score
        score = round(normalized * veto_product, 4)

        notes: list[str] = []
        if inp.veto_gates.is_blocked:
            score = 0.0
            notes.append(
                "Proposal BLOCKED — one or more veto gates returned 0.0. "
                "Score overridden to 0.0."
            )
        if inp.veto_gates.active_warnings:
            gate_names = [g.gate_type.value for g in inp.veto_gates.active_warnings]
            notes.append(f"Degraded-mode gates active: {gate_names}. Score halved.")

        return ScoringResult(
            recommendation_score=score,
            raw_weighted_sum=round(raw_sum, 4),
            veto_product=round(veto_product, 4),
            weights=weights,
            gain_vector=gains,
            veto_gates=inp.veto_gates,
            is_blocked=inp.veto_gates.is_blocked,
            score_breakdown=weighted_terms,
            notes=notes,
        )

    def compute_from_reviewers(
        self,
        cost_output: CostReviewerOutput | None,
        perf_output: PerformanceReviewerOutput | None,
        security_output: SecurityReviewerOutput | None,
        veto_gates: VetoGateSet,
        optimization_goal: OptimizationGoal = OptimizationGoal.BALANCED,
    ) -> ScoringResult:
        """
        Derive a GainVector from reviewer scores and compute the recommendation score.

        Reviewer score ∈ [0, 1] is mapped to gain ∈ [-1, 1]:
            gain = (reviewer.score - 0.5) * 2
            0.5 score → 0.0 gain (neutral)
            1.0 score → +1.0 gain (maximum improvement)
            0.0 score → -1.0 gain (maximum degradation)

        A missing reviewer (None) contributes 0.0 gain (neutral).
        A FAIL reviewer contributes -1.0 gain for its dimension.
        """
        gain = GainVector(
            cost=_reviewer_to_gain(cost_output),
            performance=_reviewer_to_gain(perf_output),
            reliability=_slo_gain(perf_output),
            security=_reviewer_to_gain(security_output),
        )
        return self.compute(ScoringInput(
            gain_vector=gain,
            veto_gates=veto_gates,
            optimization_goal=optimization_goal,
        ))


# ── helpers ───────────────────────────────────────────────────────────────────

def _reviewer_to_gain(output: ReviewerOutput | None) -> float:
    """Map reviewer score [0, 1] → gain [-1, 1]. FAIL → -1.0."""
    if output is None:
        return 0.0
    if output.status == ReviewerStatus.FAIL:
        return -1.0
    return round((output.score - 0.5) * 2.0, 4)


def _slo_gain(perf: PerformanceReviewerOutput | None) -> float:
    """
    Derive reliability gain from performance reviewer.
    FAIL → -1.0 (SLO breach). WARNING → slight negative. PASS → positive.
    """
    if perf is None:
        return 0.0
    if perf.status == ReviewerStatus.FAIL:
        return -1.0
    if perf.status == ReviewerStatus.UNKNOWN:
        return 0.0
    # Use reviewer score same as _reviewer_to_gain
    return round((perf.score - 0.5) * 2.0, 4)
