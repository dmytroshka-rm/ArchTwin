from __future__ import annotations

from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.enums import OptimizationGoal, VetoGateResult
from isa_cad.core.models.recommendation import Recommendation
from isa_cad.core.models.veto import VetoGate

# Maximum number of recommendations returned (highest goal_alignment first)
_MAX_RECOMMENDATIONS = 3

# Goal alignment boost when primary_goal matches current optimization_goal
_GOAL_MATCH_BOOST = 0.15

# Goals that conflict with cost-savings recommendations
_COST_CONFLICT_GOALS = {OptimizationGoal.MAX_RELIABILITY}

# Goals that conflict with reliability/safety recommendations
_RELIABILITY_CONFLICT_GOALS = {OptimizationGoal.COST_EFFICIENCY}


# ── Signal helpers ────────────────────────────────────────────────────────────

def _gate_result(state: AgentState, key: str) -> VetoGateResult | None:
    gate: VetoGate | None = state.get(key)  # type: ignore[literal-required]
    return gate.result if gate is not None else None


def _gate_non_passing(state: AgentState, key: str) -> bool:
    r = _gate_result(state, key)
    return r in (VetoGateResult.DEGRADED, VetoGateResult.BLOCKED)


def _gate_blocked(state: AgentState, key: str) -> bool:
    return _gate_result(state, key) == VetoGateResult.BLOCKED


# ── Goal alignment scoring ────────────────────────────────────────────────────

def _align(
    base: float,
    primary_goal: OptimizationGoal,
    current_goal: OptimizationGoal,
    conflict_goals: set[OptimizationGoal] | None = None,
) -> float:
    score = base
    if current_goal == primary_goal:
        score += _GOAL_MATCH_BOOST
    elif conflict_goals and current_goal in conflict_goals:
        score -= 0.10
    return round(min(1.0, max(0.0, score)), 3)


# ── Rule functions ────────────────────────────────────────────────────────────

def _rule_lambda_migration(state: AgentState, goal: OptimizationGoal) -> Recommendation | None:
    """Fires when cost reviewer flags FAIL or high delta."""
    cost_r = state.get("cost_review")
    if cost_r is None:
        return None
    from isa_cad.core.models.enums import ReviewerStatus
    if cost_r.status not in (ReviewerStatus.FAIL, ReviewerStatus.WARNING):
        return None
    if cost_r.score >= 0.70:
        return None  # only borderline or bad cost scores

    return Recommendation(
        id="rec.lambda-migration",
        title="Migrate high-cost services to Lambda",
        rationale=(
            f"Cost reviewer returned status={cost_r.status.value} "
            f"(score={cost_r.score:.2f}). Serverless runtime eliminates "
            "idle-capacity costs for bursty workloads."
        ),
        primary_goal=OptimizationGoal.COST_EFFICIENCY,
        goal_alignment=_align(0.75, OptimizationGoal.COST_EFFICIENCY, goal,
                               _RELIABILITY_CONFLICT_GOALS),
        trigger="cost_review.status in (warning, fail)",
        suggested_changes=[
            "Replace ECS service with Lambda + API Gateway.",
            "Set reserved concurrency to cap blast radius.",
            "Apply +15% safety buffer to projected cost estimate.",
        ],
        expected_improvements={
            "cost":        "~20–35% reduction for bursty workloads",
            "cold_start":  "mitigate with provisioned concurrency",
            "operational": "reduced cluster management overhead",
        },
    )


def _rule_read_replica(state: AgentState, goal: OptimizationGoal) -> Recommendation | None:
    """Fires when DB pressure is high."""
    perf_r = state.get("performance_review")
    if perf_r is None or perf_r.db_pressure_risk != "high":
        return None

    return Recommendation(
        id="rec.read-replica",
        title="Add read replica and connection pool to reduce DB pressure",
        rationale=(
            "PerformanceReviewerNode detected high DB pressure risk. "
            "Read replicas redirect read-heavy workloads; a connection pool "
            "prevents connection exhaustion under burst traffic."
        ),
        primary_goal=OptimizationGoal.MAX_RELIABILITY,
        goal_alignment=_align(0.78, OptimizationGoal.MAX_RELIABILITY, goal,
                               _COST_CONFLICT_GOALS),
        trigger="performance_review.db_pressure_risk == 'high'",
        suggested_changes=[
            "Provision a read replica for the shared DB.",
            "Deploy PgBouncer (or RDS Proxy) as connection pool.",
            "Route read queries to the replica endpoint.",
        ],
        expected_improvements={
            "db_pressure": "reduced — reads offloaded to replica",
            "p95_latency": "~15–25% improvement under read-heavy load",
            "reliability": "connection exhaustion prevented",
        },
    )


def _rule_async_decoupling(state: AgentState, goal: OptimizationGoal) -> Recommendation | None:
    """Fires when blast radius includes Tier-1 components."""
    br = state.get("blast_radius")
    if br is None or br.high_risk_count < 1:
        return None

    return Recommendation(
        id="rec.async-decoupling",
        title="Decouple Tier-1 components with an async event queue",
        rationale=(
            f"BlastRadiusNode identified {br.high_risk_count} high-risk Tier-1 "
            "component(s) directly reachable from the modified component. "
            "An async queue absorbs traffic spikes and isolates failures."
        ),
        primary_goal=OptimizationGoal.MAX_RELIABILITY,
        goal_alignment=_align(0.72, OptimizationGoal.MAX_RELIABILITY, goal),
        trigger="blast_radius.high_risk_count >= 1",
        suggested_changes=[
            "Introduce SQS / Kafka queue between source and Tier-1 component.",
            "Add dead-letter queue (DLQ) with CloudWatch alarm.",
            "Convert synchronous calls to async producers.",
        ],
        expected_improvements={
            "blast_radius":  "Tier-1 components isolated from direct traffic spike",
            "reliability":   "failure isolation; retries via DLQ",
            "throughput":    "queue absorbs burst without overwhelming DB",
        },
    )


def _rule_auth_middleware(state: AgentState, goal: OptimizationGoal) -> Recommendation | None:
    """Fires when security gate is non-passing and PII flow failed."""
    if not _gate_non_passing(state, "security_gate"):
        return None
    sec_r = state.get("security_review")
    if sec_r is None:
        return None
    if sec_r.pii_flow_status not in ("fail", "warning"):
        return None

    return Recommendation(
        id="rec.auth-middleware",
        title="Add auth middleware and PII data masking at API boundary",
        rationale=(
            f"SecurityVetoGate is {_gate_result(state, 'security_gate').value} "
            f"and PII flow status is '{sec_r.pii_flow_status}'. "
            "A dedicated auth middleware enforces trust boundaries; "
            "PII masking prevents leakage through public APIs."
        ),
        primary_goal=OptimizationGoal.MINIMAL_COMPLEXITY,
        goal_alignment=_align(0.80, OptimizationGoal.MINIMAL_COMPLEXITY, goal),
        trigger="security_gate non-passing and pii_flow_status in (fail, warning)",
        suggested_changes=[
            "Deploy dedicated auth/identity middleware in front of public APIs.",
            "Implement PII field masking (tokenisation or redaction) at API boundary.",
            "Add trust-zone labels to isa.yaml component graph.",
        ],
        expected_improvements={
            "pii_flow":    "pass",
            "trust_boundaries": "enforced",
            "compliance":  "improved — PII no longer crosses unprotected boundaries",
        },
    )


def _rule_provisioned_concurrency(
    state: AgentState, goal: OptimizationGoal
) -> Recommendation | None:
    """Fires when cold-start risk is high."""
    perf_r = state.get("performance_review")
    if perf_r is None or perf_r.cold_start_risk != "high":
        return None

    return Recommendation(
        id="rec.provisioned-concurrency",
        title="Configure Lambda provisioned concurrency to eliminate cold starts",
        rationale=(
            "PerformanceReviewerNode detected high cold-start risk. "
            "Provisioned concurrency keeps Lambda instances warm, "
            "removing p95/p99 latency spikes on the first requests of each burst."
        ),
        primary_goal=OptimizationGoal.MAX_RELIABILITY,
        goal_alignment=_align(0.76, OptimizationGoal.MAX_RELIABILITY, goal,
                               _COST_CONFLICT_GOALS),
        trigger="performance_review.cold_start_risk == 'high'",
        suggested_changes=[
            "Set Lambda provisioned concurrency to cover expected baseline RPS.",
            "Add EventBridge warm-up schedule for off-peak hours.",
            "Monitor ConcurrentExecutions vs ProvisionedConcurrencyUtilization.",
        ],
        expected_improvements={
            "cold_start":   "eliminated for provisioned instances",
            "p95_latency":  "improved on cold path",
            "cost":         "slight increase for provisioned capacity (~10%)",
        },
    )


def _rule_cdn_caching(state: AgentState, goal: OptimizationGoal) -> Recommendation | None:
    """Fires when bottleneck risk is high."""
    perf_r = state.get("performance_review")
    if perf_r is None or perf_r.bottleneck_risk != "high":
        return None

    return Recommendation(
        id="rec.cdn-caching",
        title="Add CDN and response caching to reduce origin load",
        rationale=(
            "PerformanceReviewerNode detected high bottleneck risk. "
            "A CDN shifts cacheable traffic to edge nodes, "
            "reducing origin load and egress costs."
        ),
        primary_goal=OptimizationGoal.COST_EFFICIENCY,
        goal_alignment=_align(0.70, OptimizationGoal.COST_EFFICIENCY, goal),
        trigger="performance_review.bottleneck_risk == 'high'",
        suggested_changes=[
            "Deploy CloudFront (or equivalent CDN) in front of public API.",
            "Increase cache TTL for static and low-volatility endpoints.",
            "Add Cache-Control headers to API responses.",
        ],
        expected_improvements={
            "throughput": "CDN absorbs cacheable traffic",
            "cost":       "egress savings (~30–50% for cacheable workloads)",
            "latency":    "reduced for cached responses (~10–50ms)",
        },
    )


def _rule_observed_graph_refresh(
    state: AgentState, goal: OptimizationGoal
) -> Recommendation | None:
    """Fires when fidelity gate is non-passing."""
    if not _gate_non_passing(state, "fidelity_gate"):
        return None

    return Recommendation(
        id="rec.observed-graph-refresh",
        title="Trigger Observed Graph refresh for higher forecast accuracy",
        rationale=(
            f"FidelityVetoGate is {_gate_result(state, 'fidelity_gate').value}. "
            "Stale or incomplete data reduces forecast confidence. "
            "A refresh replaces heuristic assumptions with real observed metrics."
        ),
        primary_goal=OptimizationGoal.BALANCED,
        goal_alignment=_align(0.68, OptimizationGoal.BALANCED, goal),
        trigger="fidelity_gate non-passing",
        suggested_changes=[
            "Initiate async Observed Graph refresh (cloud inventory + runtime metrics).",
            "Re-run the full pipeline after refresh completes.",
            "Update data_age targets in isa.yaml if sources are unavailable.",
        ],
        expected_improvements={
            "confidence":   "increased",
            "output_mode":  "final_forecast (from exploratory_estimate)",
            "assumptions":  "replaced by observed data",
        },
    )


# ── All rules ─────────────────────────────────────────────────────────────────

_RULES = [
    _rule_lambda_migration,
    _rule_read_replica,
    _rule_async_decoupling,
    _rule_auth_middleware,
    _rule_provisioned_concurrency,
    _rule_cdn_caching,
    _rule_observed_graph_refresh,
]


def generate_recommendations(
    state: AgentState,
    goal: OptimizationGoal,
    max_results: int = _MAX_RECOMMENDATIONS,
) -> list[Recommendation]:
    """
    Run all recommendation rules against the current pipeline state.
    Returns up to max_results recommendations sorted by goal_alignment descending.
    """
    results: list[Recommendation] = []
    seen_ids: set[str] = set()

    for rule in _RULES:
        rec = rule(state, goal)
        if rec is not None and rec.id not in seen_ids:
            results.append(rec)
            seen_ids.add(rec.id)

    results.sort(key=lambda r: r.goal_alignment, reverse=True)
    return results[:max_results]


# ── LangGraph node ────────────────────────────────────────────────────────────

class SandboxRecommendationNode:
    """
    LangGraph node — generates goal-driven architecture recommendations (Section 7).

    Evaluates seven heuristic rules against signals from upstream nodes and
    returns the top-3 recommendations ranked by goal_alignment:

        rec.lambda-migration          cost_review warning/fail
        rec.read-replica              db_pressure_risk == 'high'
        rec.async-decoupling          blast_radius.high_risk_count >= 1
        rec.auth-middleware           security_gate non-passing + pii fail
        rec.provisioned-concurrency   cold_start_risk == 'high'
        rec.cdn-caching               bottleneck_risk == 'high'
        rec.observed-graph-refresh    fidelity_gate non-passing

    goal_alignment = base_score [+0.15 if goal matches] [-0.10 if goal conflicts]

    Reads:
        state["optimization_goal"]      current goal (default BALANCED)
        state["cost_review"]            CostReviewerOutput
        state["performance_review"]     PerformanceReviewerOutput
        state["security_review"]        SecurityReviewerOutput
        state["blast_radius"]           BlastRadiusOutput
        state["security_gate"]          VetoGate
        state["fidelity_gate"]          VetoGate

    Writes:
        state["recommendations"]                    list[dict] (serialized Recommendations)
        state["final_output"]["recommendations"]    same (if final_output present)
    """

    def __call__(self, state: AgentState) -> AgentState:
        goal: OptimizationGoal = state.get(  # type: ignore[assignment]
            "optimization_goal", OptimizationGoal.BALANCED
        )

        recs = generate_recommendations(state, goal)
        recs_dicts: list[dict[str, Any]] = [r.model_dump() for r in recs]

        final_output: dict | None = state.get("final_output")
        if final_output is not None:
            final_output = {**final_output, "recommendations": recs_dicts}

        result = {**state, "recommendations": recs_dicts}
        if final_output is not None:
            result["final_output"] = final_output
        return result
