from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.base import EvidenceRef
from isa_cad.core.models.enums import OptimizationGoal, ReviewerStatus
from isa_cad.core.models.reviewer import Finding, PerformanceReviewerOutput
from isa_cad.state.canvas_state import ComponentGraph, ComponentNode


# ── Heuristic latency table (ms added per node traversal) ─────────────────────
# Represents the typical per-hop latency contribution of each component type.
# Based on industry P95 benchmarks; always flagged as assumptions when used.

_NODE_LATENCY_MS: dict[str, float] = {
    "service":   5.0,    # internal micro-service call (same region, HTTP/gRPC)
    "database": 10.0,    # managed database round-trip (RDS/Aurora, same AZ)
    "queue":     2.0,    # async enqueue (SQS send, SNS publish)
    "gateway":   3.0,    # API Gateway overhead
    "external":  50.0,   # 3rd-party network call (best case)
    "logging":   1.0,    # fire-and-forget log shipping
    "cache":     1.0,    # Redis GET (sub-ms, modelled conservatively)
    "storage":   8.0,    # S3 GET (same region)
    "lambda":   25.0,    # warm Lambda invocation (cold-start handled separately)
}

# Cold-start overhead added on top of warm latency (ms)
_COLD_START_OVERHEAD_MS: dict[str, float] = {
    "lambda":  200.0,    # JVM/container cold start 200-500ms; 200 conservative
}

# P99 multiplier: P99 ≈ P95 × factor
_P99_MULTIPLIER = 1.5

# Throughput heuristic (requests per second per node type — rough ceiling)
_NODE_THROUGHPUT_RPS: dict[str, float] = {
    "service":  1000.0,
    "database":  500.0,  # connection-pool limited
    "queue":    5000.0,  # async, high throughput
    "gateway":  2000.0,
    "external":  100.0,  # 3rd-party rate limit estimate
    "logging":  5000.0,
    "cache":   10000.0,
    "storage":  1000.0,
    "lambda":   200.0,   # concurrency-limited (default 1000 / 5 req avg)
}

# DB pressure: high if a database node has more than this many incoming edges
_DB_PRESSURE_EDGE_THRESHOLD = 3
# Queue pressure: queue node with more than this many producers
_QUEUE_PRESSURE_EDGE_THRESHOLD = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node_latency_ms(node: ComponentNode, include_cold_start: bool = False) -> float:
    """
    Resolve warm latency for a node.
    Checks metadata['p95_latency_ms'] first; falls back to heuristic.
    """
    if "p95_latency_ms" in node.metadata:
        base = float(node.metadata["p95_latency_ms"])
    else:
        base = _NODE_LATENCY_MS.get(node.component_type, 5.0)

    if include_cold_start:
        base += _COLD_START_OVERHEAD_MS.get(node.component_type, 0.0)

    return base


def _graph_p95_ms(graph: ComponentGraph, include_cold_start: bool = False) -> float:
    """
    Estimate P95 latency for the graph as sum of all node latencies.

    This is a conservative worst-case (assumes every node is on the critical
    path). Real critical path analysis requires topology and traffic patterns,
    which are not available without observed metrics.
    """
    return sum(_node_latency_ms(n, include_cold_start) for n in graph.nodes)


def _graph_throughput_rps(graph: ComponentGraph) -> float:
    """
    Estimate effective throughput as the minimum bottleneck across all nodes.
    The system's throughput ceiling is bounded by its weakest link.
    """
    if not graph.nodes:
        return 0.0
    return min(
        _NODE_THROUGHPUT_RPS.get(n.component_type, 1000.0)
        for n in graph.nodes
    )


def _has_cold_start_nodes(graph: ComponentGraph) -> bool:
    return any(n.component_type in _COLD_START_OVERHEAD_MS for n in graph.nodes)


def _db_pressure_risk(graph: ComponentGraph) -> str:
    """
    Detect DB pressure: a database node receiving edges from many callers.
    Returns "high" | "medium" | "low".
    """
    db_ids = {n.id for n in graph.nodes if n.component_type == "database"}
    if not db_ids:
        return "low"

    # Count incoming edges per DB node
    in_degree: dict[str, int] = {db_id: 0 for db_id in db_ids}
    for edge in graph.edges:
        if edge.target_id in in_degree:
            in_degree[edge.target_id] += 1

    max_in = max(in_degree.values(), default=0)
    if max_in > _DB_PRESSURE_EDGE_THRESHOLD:
        return "high"
    if max_in > 1:
        return "medium"
    return "low"


def _queue_pressure_risk(graph: ComponentGraph) -> str:
    """
    Detect queue pressure: many producers sending to the same queue.
    Returns "high" | "medium" | "low".
    """
    queue_ids = {n.id for n in graph.nodes if n.component_type == "queue"}
    if not queue_ids:
        return "low"

    in_degree: dict[str, int] = {q: 0 for q in queue_ids}
    for edge in graph.edges:
        if edge.target_id in in_degree:
            in_degree[edge.target_id] += 1

    max_in = max(in_degree.values(), default=0)
    if max_in > _QUEUE_PRESSURE_EDGE_THRESHOLD:
        return "high"
    if max_in > 2:
        return "medium"
    return "low"


def _tier1_bottleneck_present(graph: ComponentGraph) -> bool:
    """True if any Tier-1 node has high in-degree (shared resource contention)."""
    tier1_ids = {n.id for n in graph.nodes if n.tier == "tier_1"}
    if not tier1_ids:
        return False
    in_degree: dict[str, int] = {t: 0 for t in tier1_ids}
    for edge in graph.edges:
        if edge.target_id in in_degree:
            in_degree[edge.target_id] += 1
    return any(v > _DB_PRESSURE_EDGE_THRESHOLD for v in in_degree.values())


def _score_from_latency_delta_pct(delta_pct: float, goal: OptimizationGoal) -> float:
    """
    Map latency delta % → score [0.0, 1.0].
    Negative delta (latency reduced) → better score.
    MAX_RELIABILITY goal amplifies the weight.
    """
    clamped = max(-100.0, min(200.0, delta_pct))
    base = 0.5 - (clamped / 100.0) * 0.4
    if goal == OptimizationGoal.MAX_RELIABILITY:
        base = 0.5 - (clamped / 100.0) * 0.5
    return round(max(0.0, min(1.0, base)), 4)


def _status_from_risks(
    latency_delta_pct: float,
    db_risk: str,
    queue_risk: str,
    bottleneck: bool,
) -> ReviewerStatus:
    if latency_delta_pct > 50.0 or db_risk == "high" or queue_risk == "high" or bottleneck:
        return ReviewerStatus.FAIL
    if latency_delta_pct > 15.0 or db_risk == "medium" or queue_risk == "medium":
        return ReviewerStatus.WARNING
    return ReviewerStatus.PASS


# ── Node ──────────────────────────────────────────────────────────────────────

class PerformanceReviewerNode:
    """
    LangGraph node — runs in parallel with Cost and Security reviewers.

    Analyses performance impact of the proposed graph change:
        • P95 / P99 latency (heuristic sum over critical path nodes)
        • Throughput ceiling (weakest-link bottleneck)
        • Cold-start risk (lambda / serverless nodes)
        • DB pressure (fan-in to database nodes)
        • Queue pressure (fan-in to queue nodes)
        • Tier-1 contention risk

    All estimates are heuristic and flagged as assumptions when no observed
    metrics are present in node.metadata.

    Outputs written to state["performance_review"].
    """

    def __call__(self, state: AgentState) -> AgentState:
        session  = state.get("canvas_session")
        resolved = state.get("resolved_graph")
        goal     = state.get("optimization_goal", OptimizationGoal.BALANCED)

        if session is None or resolved is None:
            output = PerformanceReviewerOutput(
                status=ReviewerStatus.UNKNOWN,
                score=0.5,
                confidence=0.0,
                recommendation="No session or graph available for performance analysis.",
                missing_inputs=["canvas_session", "resolved_graph"],
            )
            return {**state, "performance_review": output}

        baseline = session.baseline_graph
        proposed = resolved

        # ── Latency estimates ─────────────────────────────────────────────────
        p95_base = _graph_p95_ms(baseline)
        p95_prop = _graph_p95_ms(proposed)

        # Include cold-start overhead for P99 on proposed path
        cold_start_present = _has_cold_start_nodes(proposed)
        p99_base = round(p95_base * _P99_MULTIPLIER, 2)
        p99_prop = round(
            _graph_p95_ms(proposed, include_cold_start=cold_start_present)
            * _P99_MULTIPLIER,
            2,
        )

        latency_delta_ms  = round(p95_prop - p95_base, 2)
        latency_delta_pct = (
            round(latency_delta_ms / p95_base * 100.0, 2) if p95_base > 0 else 0.0
        )
        latency_delta_str = (
            f"{'+' if latency_delta_ms >= 0 else ''}{latency_delta_ms:.1f}ms "
            f"({'+' if latency_delta_pct >= 0 else ''}{latency_delta_pct:.1f}%)"
        )

        # ── Risk analysis ─────────────────────────────────────────────────────
        db_risk    = _db_pressure_risk(proposed)
        queue_risk = _queue_pressure_risk(proposed)
        tier1_risk = _tier1_bottleneck_present(proposed)
        throughput = _graph_throughput_rps(proposed)
        cold_risk  = "high" if cold_start_present else "low"

        # ── Status / score ────────────────────────────────────────────────────
        status = _status_from_risks(latency_delta_pct, db_risk, queue_risk, tier1_risk)
        score  = _score_from_latency_delta_pct(latency_delta_pct, goal)

        # Penalise score for structural risks
        if db_risk == "high":
            score = max(0.0, round(score - 0.15, 4))
        elif db_risk == "medium":
            score = max(0.0, round(score - 0.07, 4))
        if queue_risk == "high":
            score = max(0.0, round(score - 0.10, 4))
        if tier1_risk:
            score = max(0.0, round(score - 0.10, 4))

        # ── Confidence ────────────────────────────────────────────────────────
        confidence = self._compute_confidence(proposed)

        # ── Findings + evidence ───────────────────────────────────────────────
        findings = self._build_findings(
            latency_delta_ms, latency_delta_pct,
            db_risk, queue_risk, cold_risk, tier1_risk,
            p95_base, p95_prop, throughput,
        )
        evidence = self._build_evidence(p95_base, p95_prop, throughput, proposed)
        assumptions = self._collect_assumptions(proposed)

        recommendation = self._build_recommendation(
            latency_delta_pct, latency_delta_ms, status, db_risk, queue_risk,
        )

        output = PerformanceReviewerOutput(
            status=status,
            score=score,
            confidence=confidence,
            findings=findings,
            evidence=evidence,
            assumptions=assumptions,
            recommendation=recommendation,
            latency_delta=latency_delta_str,
            p95_baseline_ms=round(p95_base, 2),
            p95_projected_ms=round(p95_prop, 2),
            p99_baseline_ms=p99_base,
            p99_projected_ms=p99_prop,
            throughput_rps=round(throughput, 2),
            bottleneck_risk="high" if tier1_risk else db_risk,
            cold_start_risk=cold_risk,
            db_pressure_risk=db_risk,
            queue_pressure_risk=queue_risk,
        )

        return {**state, "performance_review": output}

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(graph: ComponentGraph) -> float:
        """
        Confidence starts at 1.0; reduced when heuristics are used instead of
        observed P95 metrics.
        """
        observed = sum(
            1 for n in graph.nodes if "p95_latency_ms" in n.metadata
        )
        total = max(1, len(graph.nodes))
        ratio = observed / total
        # Full observed → 0.90 (topology still unknown); full heuristic → 0.35
        confidence = 0.35 + ratio * 0.55
        return round(min(0.90, confidence), 4)

    @staticmethod
    def _build_findings(
        delta_ms: float,
        delta_pct: float,
        db_risk: str,
        queue_risk: str,
        cold_risk: str,
        tier1_risk: bool,
        p95_base: float,
        p95_prop: float,
        throughput: float,
    ) -> list[Finding]:
        findings: list[Finding] = []

        # Latency regression
        if delta_ms > 0 and delta_pct > 50.0:
            findings.append(Finding(
                severity="high",
                title="Significant latency regression",
                description=(
                    f"Estimated P95 latency increases by {delta_ms:.1f}ms "
                    f"({delta_pct:.1f}%): {p95_base:.1f}ms → {p95_prop:.1f}ms."
                ),
                recommendation=(
                    "Profile critical path. Consider caching, async patterns, "
                    "or removing high-latency nodes from the hot path."
                ),
            ))
        elif delta_ms > 0 and delta_pct > 15.0:
            findings.append(Finding(
                severity="medium",
                title="Moderate latency increase",
                description=(
                    f"Estimated P95 increases by {delta_ms:.1f}ms ({delta_pct:.1f}%). "
                    f"{p95_base:.1f}ms → {p95_prop:.1f}ms."
                ),
                recommendation="Acceptable if within SLA budget. Monitor P95 after deploy.",
            ))
        elif delta_ms < 0:
            findings.append(Finding(
                severity="info",
                title="Latency improvement detected",
                description=(
                    f"Proposed graph reduces estimated P95 by {abs(delta_ms):.1f}ms "
                    f"({abs(delta_pct):.1f}%). {p95_base:.1f}ms → {p95_prop:.1f}ms."
                ),
                recommendation="Proceed — latency profile improved.",
            ))

        # DB pressure
        if db_risk == "high":
            findings.append(Finding(
                severity="high",
                title="High database fan-in detected",
                description=(
                    f"A database node receives connections from more than "
                    f"{_DB_PRESSURE_EDGE_THRESHOLD} callers. "
                    "Risk of connection pool exhaustion and query contention."
                ),
                recommendation=(
                    "Introduce a read replica, connection pooler (PgBouncer/RDS Proxy), "
                    "or a caching layer in front of the database."
                ),
            ))
        elif db_risk == "medium":
            findings.append(Finding(
                severity="medium",
                title="Moderate database fan-in",
                description="Multiple services call the same database directly.",
                recommendation=(
                    "Consider read replicas or a DAL (Data Access Layer) "
                    "to avoid future contention."
                ),
            ))

        # Queue pressure
        if queue_risk == "high":
            findings.append(Finding(
                severity="high",
                title="High queue producer fan-in",
                description=(
                    f"A queue node receives messages from more than "
                    f"{_QUEUE_PRESSURE_EDGE_THRESHOLD} producers. "
                    "Risk of backpressure and consumer lag."
                ),
                recommendation=(
                    "Partition queue by domain, or introduce a fan-out topic "
                    "to distribute load."
                ),
            ))
        elif queue_risk == "medium":
            findings.append(Finding(
                severity="low",
                title="Moderate queue producer count",
                description="Several producers send to the same queue.",
                recommendation="Monitor consumer lag metrics post-deploy.",
            ))

        # Cold start
        if cold_risk == "high":
            findings.append(Finding(
                severity="medium",
                title="Cold-start latency risk",
                description=(
                    "Serverless or lambda nodes in the proposed graph may add "
                    f"{_COLD_START_OVERHEAD_MS.get('lambda', 200):.0f}ms+ "
                    "P99 overhead on cold invocations."
                ),
                recommendation=(
                    "Enable provisioned concurrency for latency-critical paths, "
                    "or move warm-path logic to a container-based service."
                ),
            ))

        # Tier-1 contention
        if tier1_risk:
            findings.append(Finding(
                severity="high",
                title="Tier-1 shared resource contention",
                description=(
                    "A Tier-1 component (criticality multiplier 2.0) has high "
                    "fan-in. Degradation here cascades to all dependants."
                ),
                recommendation=(
                    "Isolate Tier-1 access behind a dedicated service or apply "
                    "circuit-breaker / bulkhead patterns."
                ),
            ))

        # Throughput ceiling
        if throughput <= 100.0:
            findings.append(Finding(
                severity="medium",
                title="Low estimated throughput ceiling",
                description=(
                    f"Weakest-link throughput estimate: {throughput:.0f} RPS. "
                    "An external dependency or low-concurrency component limits scale."
                ),
                recommendation=(
                    "Review external service rate limits and consider async "
                    "decoupling or caching."
                ),
            ))

        # Heuristic coverage note
        findings.append(Finding(
            severity="info",
            title="Latency estimates are heuristic",
            description=(
                "P95/P99 values are computed from a per-component-type latency "
                "table, not from observed APM data. Actual latency depends on "
                "network topology, traffic patterns, and load."
            ),
            recommendation=(
                "Instrument services with APM (OpenTelemetry / X-Ray) and "
                "supply observed p95_latency_ms in node metadata for higher accuracy."
            ),
        ))

        return findings

    @staticmethod
    def _build_evidence(
        p95_base: float,
        p95_prop: float,
        throughput: float,
        graph: ComponentGraph,
    ) -> list[EvidenceRef]:
        observed_nodes = [n for n in graph.nodes if "p95_latency_ms" in n.metadata]
        is_assumption  = len(observed_nodes) < len(graph.nodes)

        evidence = [
            EvidenceRef(
                source="heuristic_latency_table",
                description=(
                    f"P95 baseline={p95_base:.1f}ms, proposed={p95_prop:.1f}ms. "
                    f"Throughput ceiling={throughput:.0f} RPS. "
                    f"Observed metrics for {len(observed_nodes)}/{len(graph.nodes)} nodes."
                ),
                value={"p95_baseline_ms": p95_base, "p95_proposed_ms": p95_prop},
                is_assumption=is_assumption,
            )
        ]

        if observed_nodes:
            evidence.append(EvidenceRef(
                source="node_metadata_p95",
                description=(
                    f"Observed P95 values from metadata: "
                    + ", ".join(
                        f"{n.id}={n.metadata['p95_latency_ms']}ms"
                        for n in observed_nodes
                    )
                ),
                value={n.id: n.metadata["p95_latency_ms"] for n in observed_nodes},
                is_assumption=False,
            ))

        return evidence

    @staticmethod
    def _collect_assumptions(graph: ComponentGraph) -> list[str]:
        heuristic_nodes = [n for n in graph.nodes if "p95_latency_ms" not in n.metadata]
        if not heuristic_nodes:
            return []
        return [
            f"P95 latency for {n.id} ({n.component_type}) estimated from heuristic "
            f"table ({_NODE_LATENCY_MS.get(n.component_type, 5.0):.0f}ms). "
            "No observed APM data available."
            for n in heuristic_nodes
        ]

    @staticmethod
    def _build_recommendation(
        delta_pct: float,
        delta_ms: float,
        status: ReviewerStatus,
        db_risk: str,
        queue_risk: str,
    ) -> str:
        sign = "+" if delta_ms >= 0 else ""
        direction = "increases" if delta_ms > 0 else "decreases" if delta_ms < 0 else "unchanged"

        if status == ReviewerStatus.PASS:
            return (
                f"Performance impact is acceptable: estimated P95 {direction} by "
                f"{sign}{delta_ms:.1f}ms ({sign}{delta_pct:.1f}%). "
                "No critical bottlenecks detected."
            )
        if status == ReviewerStatus.WARNING:
            parts = [f"Moderate performance concern: P95 {sign}{delta_ms:.1f}ms ({sign}{delta_pct:.1f}%)."]
            if db_risk == "medium":
                parts.append("DB fan-in is moderate.")
            if queue_risk == "medium":
                parts.append("Queue producer count is elevated.")
            return " ".join(parts)
        # FAIL
        parts = [f"Performance review FAIL: P95 {sign}{delta_ms:.1f}ms ({sign}{delta_pct:.1f}%)."]
        if db_risk == "high":
            parts.append("High DB fan-in — connection pool risk.")
        if queue_risk == "high":
            parts.append("High queue fan-in — backpressure risk.")
        return " ".join(parts)
