from __future__ import annotations

from isa_cad.agent.graph_state import AgentState
from isa_cad.core.models.base import EvidenceRef
from isa_cad.core.models.enums import OptimizationGoal, ReviewerStatus
from isa_cad.core.models.reviewer import Finding, SecurityReviewerOutput
from isa_cad.state.canvas_state import ComponentEdge, ComponentGraph, ComponentNode


# ── Component type classification ──────────────────────────────────────────────

# Types considered public-facing (accessible from internet / external clients)
_PUBLIC_FACING_TYPES = {"gateway", "external"}

# Types that handle authentication / authorisation — high trust boundary sensitivity
# Note: "gateway" is intentionally excluded — it is a public entry point, not an auth service.
_AUTH_TYPES = {"auth", "identity"}

# Types that commonly handle PII or sensitive data
_PII_SENSITIVE_TYPES = {"database", "storage", "queue"}

# Types that imply IAM-bound access (cloud resources) — over-permissive risk
_IAM_BOUND_TYPES = {"lambda", "storage", "queue", "database"}

# Tier → trust weight: Tier-1 violations are more severe
_TIER_WEIGHT = {"tier_1": 2.0, "standard": 1.0, "auxiliary": 0.5}


# ── Trust boundary helpers ────────────────────────────────────────────────────

def _is_cross_boundary_edge(
    src: ComponentNode,
    tgt: ComponentNode,
) -> str | None:
    """
    Return a violation description if the edge crosses a trust boundary,
    else None.

    Trust boundaries (per convention Sections 5 & 8):
      1. Public-facing → internal database/queue (no service layer)
      2. External → Tier-1 (bypasses standard + auxiliary layers)
      3. Non-auth service → auth/identity node (unexpected IAM flow)
    """
    src_t = src.component_type
    tgt_t = tgt.component_type

    # Rule 1: internet-facing component writes directly to DB / queue / storage
    if src_t in _PUBLIC_FACING_TYPES and tgt_t in _PII_SENSITIVE_TYPES:
        return (
            f"{src.id} ({src_t}) → {tgt.id} ({tgt_t}): "
            "public-facing component accesses data store without service layer."
        )

    # Rule 2: external node (3rd-party) reaches Tier-1 directly
    if src_t == "external" and tgt.tier == "tier_1":
        return (
            f"{src.id} (external) → {tgt.id} (tier_1): "
            "3rd-party dependency has direct access to a Tier-1 resource."
        )

    # Rule 3: unclassified service writes to auth/identity node
    if tgt_t in _AUTH_TYPES and src_t not in _AUTH_TYPES | _PUBLIC_FACING_TYPES:
        return (
            f"{src.id} ({src_t}) → {tgt.id} ({tgt_t}): "
            "non-auth service routes through auth/identity node — unexpected IAM flow."
        )

    return None


def _detect_trust_violations(graph: ComponentGraph) -> list[str]:
    node_map = {n.id: n for n in graph.nodes}
    violations: list[str] = []
    for edge in graph.edges:
        src = node_map.get(edge.source_id)
        tgt = node_map.get(edge.target_id)
        if src and tgt:
            v = _is_cross_boundary_edge(src, tgt)
            if v:
                violations.append(v)
    return violations


# ── Public exposure ───────────────────────────────────────────────────────────

def _public_exposure_risk(graph: ComponentGraph) -> str:
    """
    Assess public exposure risk based on which node types are reachable
    from public-facing components via direct edges.

    Returns "high" | "medium" | "low".
    """
    public_ids = {n.id for n in graph.nodes if n.component_type in _PUBLIC_FACING_TYPES}
    if not public_ids:
        return "low"

    node_map = {n.id: n for n in graph.nodes}
    directly_exposed: list[ComponentNode] = []
    for edge in graph.edges:
        if edge.source_id in public_ids:
            tgt = node_map.get(edge.target_id)
            if tgt:
                directly_exposed.append(tgt)

    # High: any data store or Tier-1 node directly reachable from public
    if any(
        n.component_type in _PII_SENSITIVE_TYPES or n.tier == "tier_1"
        for n in directly_exposed
    ):
        return "high"

    # Medium: public entry points exist but only reach internal services
    if directly_exposed:
        return "medium"

    # Public nodes with no outbound edges — isolated, still flag
    return "medium"


# ── IAM scope risk ────────────────────────────────────────────────────────────

def _iam_scope_risk(graph: ComponentGraph) -> str:
    """
    Detect over-permissive IAM patterns from graph topology.

    Returns "high" | "medium" | "low".
    """
    iam_nodes = [n for n in graph.nodes if n.component_type in _IAM_BOUND_TYPES]
    if not iam_nodes:
        return "low"

    node_map = {n.id: n for n in graph.nodes}

    # Count distinct callers per IAM-bound node
    in_degree: dict[str, set[str]] = {n.id: set() for n in iam_nodes}
    for edge in graph.edges:
        if edge.target_id in in_degree:
            in_degree[edge.target_id].add(edge.source_id)

    max_callers = max((len(v) for v in in_degree.values()), default=0)

    # High: IAM-bound resource called by many distinct services (blast radius)
    if max_callers > 4:
        return "high"
    if max_callers > 2:
        return "medium"

    # Also check: lambda / storage nodes with no explicit caller (orphan IAM)
    orphan_iam = [
        n for n in iam_nodes
        if len(in_degree[n.id]) == 0 and n.component_type in {"lambda", "storage"}
    ]
    if orphan_iam:
        return "medium"   # unexplained IAM resource — needs review

    return "low"


# ── PII flow status ───────────────────────────────────────────────────────────

def _pii_flow_status(graph: ComponentGraph) -> str:
    """
    Determine PII flow status.

    Reads metadata['handles_pii'] = true/false per node.
    If any PII-bearing node is reachable from a public-facing or external node
    without passing through an auth/identity node → fail.
    If no PII metadata present → unknown.
    """
    pii_nodes = {
        n.id
        for n in graph.nodes
        if str(n.metadata.get("handles_pii", "")).lower() in ("true", "1", "yes")
    }

    if not pii_nodes:
        # Check implicit PII: databases + storage default to "may handle PII"
        implicit = {n.id for n in graph.nodes if n.component_type in {"database", "storage"}}
        if not implicit:
            return "unknown"
        pii_nodes = implicit

    node_map = {n.id: n for n in graph.nodes}
    public_ids = {n.id for n in graph.nodes if n.component_type in _PUBLIC_FACING_TYPES}
    auth_ids   = {n.id for n in graph.nodes if n.component_type in _AUTH_TYPES}

    # Build adjacency for reachability check
    adj: dict[str, set[str]] = {n.id: set() for n in graph.nodes}
    for edge in graph.edges:
        adj[edge.source_id].add(edge.target_id)

    # BFS from each public node: does any path reach PII without auth?
    for start in public_ids:
        visited: set[str] = set()
        stack = [start]
        auth_passed = False
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if current in auth_ids:
                auth_passed = True
            if current in pii_nodes and not auth_passed:
                return "fail"
            for neighbour in adj.get(current, set()):
                stack.append(neighbour)

    return "pass"


# ── Data residency ────────────────────────────────────────────────────────────

def _data_residency_status(graph: ComponentGraph) -> str:
    """
    Check data residency constraints.

    Reads metadata['region'] per node.  If an external node connects to a
    data store in a different region, flag as 'warning'.
    If no region metadata present → 'unknown'.
    """
    nodes_with_region = [n for n in graph.nodes if "region" in n.metadata]
    if not nodes_with_region:
        return "unknown"

    node_map = {n.id: n for n in graph.nodes}
    for edge in graph.edges:
        src = node_map.get(edge.source_id)
        tgt = node_map.get(edge.target_id)
        if src and tgt:
            src_region = src.metadata.get("region")
            tgt_region = tgt.metadata.get("region")
            if (
                src_region
                and tgt_region
                and src_region != tgt_region
                and tgt.component_type in _PII_SENSITIVE_TYPES
            ):
                return "warning"

    return "pass"


# ── Compliance status ─────────────────────────────────────────────────────────

def _compliance_status(
    violations: list[str],
    pii_status: str,
    exposure_risk: str,
) -> str:
    """
    Aggregate compliance status from trust violations, PII flow, and exposure.

    Returns "pass" | "warning" | "fail" | "unknown".
    """
    if violations or pii_status == "fail" or exposure_risk == "high":
        return "fail"
    if pii_status == "warning" or exposure_risk == "medium":
        return "warning"
    if pii_status == "unknown":
        return "unknown"
    return "pass"


# ── Score / status ────────────────────────────────────────────────────────────

def _score_from_security_signals(
    violations: list[str],
    exposure_risk: str,
    iam_risk: str,
    pii_status: str,
) -> float:
    """
    Penalty-based scoring starting from 1.0.
    Each negative signal deducts a weighted penalty.
    """
    score = 1.0

    # Trust boundary violations — most severe
    score -= len(violations) * 0.20

    exposure_penalty = {"high": 0.30, "medium": 0.15, "low": 0.0}
    score -= exposure_penalty.get(exposure_risk, 0.0)

    iam_penalty = {"high": 0.20, "medium": 0.10, "low": 0.0}
    score -= iam_penalty.get(iam_risk, 0.0)

    pii_penalty = {"fail": 0.25, "warning": 0.10, "pass": 0.0, "unknown": 0.05}
    score -= pii_penalty.get(pii_status, 0.05)

    return round(max(0.0, min(1.0, score)), 4)


def _status_from_security_score(
    score: float,
    violations: list[str],
    compliance: str,
) -> ReviewerStatus:
    if violations or compliance == "fail" or score < 0.40:
        return ReviewerStatus.FAIL
    if score < 0.70 or compliance == "warning":
        return ReviewerStatus.WARNING
    return ReviewerStatus.PASS


# ── Node ──────────────────────────────────────────────────────────────────────

class SecurityReviewerNode:
    """
    LangGraph node — runs in parallel with Cost and Performance reviewers.

    Analyses security posture of the proposed architecture change:
        • Public exposure risk  (internet-reachable components / topology)
        • Trust boundary violations  (public → data store without service layer)
        • IAM scope risk  (over-permissive access patterns)
        • PII flow status  (PII accessible without auth layer)
        • Data residency  (cross-region data store access)
        • Compliance aggregate  (all above signals combined)

    All analysis is structural / topological.  No credentials or secrets are
    read.  The Metadata First convention is strictly observed — PII and region
    metadata are optional hints only.

    Outputs written to state["security_review"].
    """

    def __call__(self, state: AgentState) -> AgentState:
        session  = state.get("canvas_session")
        resolved = state.get("resolved_graph")

        if session is None or resolved is None:
            output = SecurityReviewerOutput(
                status=ReviewerStatus.UNKNOWN,
                score=0.5,
                confidence=0.0,
                recommendation="No session or graph available for security analysis.",
                missing_inputs=["canvas_session", "resolved_graph"],
            )
            return {**state, "security_review": output}

        proposed = resolved

        # ── Analysis ──────────────────────────────────────────────────────────
        violations   = _detect_trust_violations(proposed)
        exposure     = _public_exposure_risk(proposed)
        iam_risk     = _iam_scope_risk(proposed)
        pii_status   = _pii_flow_status(proposed)
        residency    = _data_residency_status(proposed)
        compliance   = _compliance_status(violations, pii_status, exposure)

        score      = _score_from_security_signals(violations, exposure, iam_risk, pii_status)
        status     = _status_from_security_score(score, violations, compliance)
        confidence = self._compute_confidence(proposed)

        findings   = self._build_findings(
            violations, exposure, iam_risk, pii_status, residency,
        )
        evidence   = self._build_evidence(proposed, violations, exposure)
        assumptions = self._collect_assumptions(proposed)

        recommendation = self._build_recommendation(
            status, violations, exposure, iam_risk, pii_status,
        )

        output = SecurityReviewerOutput(
            status=status,
            score=score,
            confidence=confidence,
            findings=findings,
            evidence=evidence,
            assumptions=assumptions,
            recommendation=recommendation,
            public_exposure_risk=exposure,
            iam_scope_risk=iam_risk,
            trust_boundary_violations=violations,
            pii_flow_status=pii_status,
            data_residency_status=residency,
            compliance_status=compliance,
        )

        return {**state, "security_review": output}

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(graph: ComponentGraph) -> float:
        """
        Confidence is structural-only (topology is always available).
        Increases when nodes carry security metadata hints.
        """
        enriched = sum(
            1
            for n in graph.nodes
            if "handles_pii" in n.metadata or "region" in n.metadata
        )
        total = max(1, len(graph.nodes))
        ratio = enriched / total
        # 0.50 base (topology only) → 0.85 when all nodes have metadata
        return round(0.50 + ratio * 0.35, 4)

    @staticmethod
    def _build_findings(
        violations: list[str],
        exposure: str,
        iam_risk: str,
        pii_status: str,
        residency: str,
    ) -> list[Finding]:
        findings: list[Finding] = []

        # Trust boundary violations
        for v in violations:
            findings.append(Finding(
                severity="critical",
                title="Trust boundary violation",
                description=v,
                recommendation=(
                    "Insert a service layer or API gateway between the caller "
                    "and the data store. Apply network segmentation (VPC, security groups)."
                ),
            ))

        # Public exposure
        if exposure == "high":
            findings.append(Finding(
                severity="critical",
                title="High public exposure risk",
                description=(
                    "A public-facing or external component has direct access to "
                    "a data store or Tier-1 resource."
                ),
                recommendation=(
                    "Introduce a WAF / API Gateway layer. Restrict inbound rules "
                    "to known CIDR ranges. Apply least-privilege networking."
                ),
            ))
        elif exposure == "medium":
            findings.append(Finding(
                severity="high",
                title="Moderate public exposure",
                description=(
                    "Public-facing entry points exist and reach internal services."
                ),
                recommendation=(
                    "Ensure all public endpoints are behind an API Gateway with "
                    "auth (OAuth2 / API key). Enable request throttling."
                ),
            ))

        # IAM scope
        if iam_risk == "high":
            findings.append(Finding(
                severity="high",
                title="Over-permissive IAM scope",
                description=(
                    "An IAM-bound resource (Lambda, S3, queue, database) is "
                    "called by more than 4 distinct services — potential blast radius."
                ),
                recommendation=(
                    "Apply IAM role scoping per service. Use resource-based policies "
                    "and avoid wildcard permissions."
                ),
            ))
        elif iam_risk == "medium":
            findings.append(Finding(
                severity="medium",
                title="Elevated IAM access breadth",
                description=(
                    "Multiple services share access to IAM-bound resources. "
                    "Orphaned IAM resources may also be present."
                ),
                recommendation=(
                    "Audit IAM roles for least-privilege. Remove unused permissions "
                    "and enable CloudTrail / IAM Access Analyzer."
                ),
            ))

        # PII flow
        if pii_status == "fail":
            findings.append(Finding(
                severity="critical",
                title="PII accessible without authentication layer",
                description=(
                    "A data store handling PII is reachable from a public-facing "
                    "component without passing through an auth/identity node."
                ),
                recommendation=(
                    "Enforce authentication on all paths to PII-bearing data stores. "
                    "Add an identity/auth node on the access path."
                ),
            ))
        elif pii_status == "warning":
            findings.append(Finding(
                severity="high",
                title="PII flow requires review",
                description="PII-handling nodes have ambiguous access controls.",
                recommendation="Trace PII data flows and confirm auth coverage.",
            ))
        elif pii_status == "unknown":
            findings.append(Finding(
                severity="info",
                title="PII handling not declared in metadata",
                description=(
                    "No node declares handles_pii=true. Databases and storage nodes "
                    "are assumed to potentially handle PII."
                ),
                recommendation=(
                    "Add handles_pii metadata to all nodes that process personal data "
                    "to enable accurate PII flow analysis."
                ),
            ))

        # Data residency
        if residency == "warning":
            findings.append(Finding(
                severity="medium",
                title="Cross-region data store access detected",
                description=(
                    "An edge crosses regional boundaries to reach a data store. "
                    "May violate GDPR / data sovereignty requirements."
                ),
                recommendation=(
                    "Ensure data residency requirements allow cross-region access, "
                    "or replicate the data store to the required region."
                ),
            ))

        # Topology-only analysis note
        findings.append(Finding(
            severity="info",
            title="Security analysis is topology-based",
            description=(
                "This review uses graph structure and metadata hints only. "
                "No runtime IAM policies, TLS config, or secrets were evaluated."
            ),
            recommendation=(
                "Supplement with a live CSPM scan (AWS Security Hub / "
                "GCP Security Command Center) and a secrets audit."
            ),
        ))

        return findings

    @staticmethod
    def _build_evidence(
        graph: ComponentGraph,
        violations: list[str],
        exposure: str,
    ) -> list[EvidenceRef]:
        public_nodes = [n for n in graph.nodes if n.component_type in _PUBLIC_FACING_TYPES]
        iam_nodes    = [n for n in graph.nodes if n.component_type in _IAM_BOUND_TYPES]

        evidence = [
            EvidenceRef(
                source="graph_topology",
                description=(
                    f"Topology analysis: {len(public_nodes)} public-facing node(s), "
                    f"{len(iam_nodes)} IAM-bound node(s), "
                    f"{len(violations)} trust violation(s). "
                    f"Public exposure: {exposure}."
                ),
                value={
                    "public_node_count": len(public_nodes),
                    "iam_bound_count":   len(iam_nodes),
                    "violation_count":   len(violations),
                    "exposure_risk":     exposure,
                },
                is_assumption=False,
            )
        ]

        pii_nodes = [n for n in graph.nodes if "handles_pii" in n.metadata]
        if pii_nodes:
            evidence.append(EvidenceRef(
                source="node_metadata_pii",
                description=(
                    f"PII metadata declared on: "
                    + ", ".join(n.id for n in pii_nodes)
                ),
                value={n.id: n.metadata["handles_pii"] for n in pii_nodes},
                is_assumption=False,
            ))

        return evidence

    @staticmethod
    def _collect_assumptions(graph: ComponentGraph) -> list[str]:
        assumptions: list[str] = []

        # No PII metadata → implicit assumption
        pii_declared = any("handles_pii" in n.metadata for n in graph.nodes)
        if not pii_declared:
            assumptions.append(
                "No handles_pii metadata on any node. "
                "Databases and storage nodes assumed to potentially handle PII."
            )

        # No region metadata → residency unknown
        region_declared = any("region" in n.metadata for n in graph.nodes)
        if not region_declared:
            assumptions.append(
                "No region metadata on any node. "
                "Data residency analysis is unavailable."
            )

        # Auth type inferred from component_type string
        auth_nodes = [n for n in graph.nodes if n.component_type in _AUTH_TYPES]
        if auth_nodes:
            assumptions.append(
                f"Auth/identity classification based on component_type keyword match "
                f"for: {[n.id for n in auth_nodes]}. "
                "Confirm these nodes enforce authentication."
            )

        return assumptions

    @staticmethod
    def _build_recommendation(
        status: ReviewerStatus,
        violations: list[str],
        exposure: str,
        iam_risk: str,
        pii_status: str,
    ) -> str:
        if status == ReviewerStatus.PASS:
            return (
                "Security posture is acceptable. No trust boundary violations detected. "
                "Proceed with standard secure-deployment checklist."
            )

        parts: list[str] = ["Security review"]
        if status == ReviewerStatus.FAIL:
            parts[0] += " FAIL:"
        else:
            parts[0] += " WARNING:"

        if violations:
            parts.append(f"{len(violations)} trust boundary violation(s) require remediation.")
        if exposure == "high":
            parts.append("High public exposure — data stores reachable from internet.")
        elif exposure == "medium":
            parts.append("Public entry points present — verify auth coverage.")
        if iam_risk == "high":
            parts.append("IAM blast radius too broad — apply least-privilege.")
        if pii_status == "fail":
            parts.append("PII reachable without auth — MUST fix before deploy.")

        return " ".join(parts)
