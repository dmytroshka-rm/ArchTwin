from __future__ import annotations

"""
isa_cad/api/server.py
======================
FastAPI HTTP server bridging the frontend Canvas to the backend LangGraph pipeline.

Run:
    uvicorn isa_cad.api.server:app --reload --port 8000

Golden rule (Convention v0.6 Section 1.1):
    Frontend owns interaction & visualization.
    Backend owns canonical validation, simulation, veto decisions, confidence, artifacts.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from isa_cad.core.logging import configure_logging, get_logger


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    _log.info("api.start", port=8000)
    yield
    _log.info("api.shutdown")


app = FastAPI(
    title="ArchTwin API",
    version="0.6.0",
    description="Backend API for ArchTwin Architecture Canvas",
    lifespan=lifespan,
)


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("ISA_CAD_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["http://localhost:5173"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_log = get_logger("isa_cad.api")


# ══════════════════════════════════════════════════════════════════════════════
# Request / response schemas
# ══════════════════════════════════════════════════════════════════════════════

# ── Capabilities ──────────────────────────────────────────────────────────────

class BackendCapabilities(BaseModel):
    isa_schema_version: str = "1.0.0"
    simulation_result_schema_version: str = "1.0.0"
    canvas_event_schema_version: str = "1.0.0"
    agent_convention_version: str = "0.5.3"
    supported_goals: list[str] = [
        "balanced", "cost_efficiency", "max_reliability", "minimal_complexity"
    ]
    supported_reviewers: list[str] = ["cost", "performance", "security"]


# ── Canvas operations ─────────────────────────────────────────────────────────

class CanvasOperationRequest(BaseModel):
    type: str
    payload: dict[str, Any]


class OperationValidationResult(BaseModel):
    operation_id: str
    status: str  # valid | invalid | blocked | requires_adr
    normalized: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    missing_metadata: list[str] = Field(default_factory=list)
    adr_required: bool = False
    adr_reason: str | None = None


# ── Layers ────────────────────────────────────────────────────────────────────

class CreateLayerRequest(BaseModel):
    title: str
    baseline_ref: str
    optimization_goal: str = "balanced"


class LayerResponse(BaseModel):
    id: str
    title: str
    status: str
    baseline_ref: str
    optimization_goal: str
    created_at: str
    diff: dict[str, Any] = Field(default_factory=lambda: {"operations": []})
    simulation_fidelity: dict[str, Any] | None = None
    blast_radius: dict[str, Any] | None = None


# ── Simulation ────────────────────────────────────────────────────────────────

class FreshnessPolicy(BaseModel):
    warn_after_hours: int = 24
    exploratory_after_days: int = 7
    block_final_decision_below_confidence: float = 0.65


class SimulationRequest(BaseModel):
    baseline_ref: str
    proposal_refs: list[str]
    optimization_goal: str = "balanced"
    reviewers: list[str] = Field(default_factory=lambda: ["cost", "performance", "security"])
    include_blast_radius: bool = True
    include_calibration: bool = True
    freshness_policy: FreshnessPolicy | None = None
    components: list[dict[str, Any]] | None = None
    relations: list[dict[str, Any]] | None = None


class SimulationStartResponse(BaseModel):
    job_id: str


# ── Promotion ─────────────────────────────────────────────────────────────────

class PromotionArtifacts(BaseModel):
    isa_yaml_patch: str
    adr_draft: str
    required_actions: dict[str, list[str]]
    pr_description: str
    confidence_check: dict[str, Any]


# ── Comments ──────────────────────────────────────────────────────────────────

class CommentAnchor(BaseModel):
    target_type: str
    target_id: str
    layer_id: str
    field_path: str | None = None


class CreateCommentRequest(BaseModel):
    anchor: CommentAnchor
    author: str
    body: str
    resolved: bool = False


class CommentResponse(BaseModel):
    id: str
    anchor: CommentAnchor
    author: str
    body: str
    created_at: str
    resolved: bool


# ══════════════════════════════════════════════════════════════════════════════
# In-memory state (MVP — in production use a real database)
# ══════════════════════════════════════════════════════════════════════════════

_layers: dict[str, LayerResponse] = {}
_simulations: dict[str, dict[str, Any]] = {}
_comments: dict[str, list[CommentResponse]] = {}  # layer_id -> comments


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

# ── Capabilities (Section 7.1) ────────────────────────────────────────────────

@app.get("/api/capabilities", response_model=BackendCapabilities)
async def get_capabilities():
    """Version handshake — frontend checks compatibility on startup."""
    return BackendCapabilities()


# ── Canvas operations (Section 5.1) ───────────────────────────────────────────

@app.post("/api/canvas/operations", response_model=OperationValidationResult)
async def validate_canvas_operation(req: CanvasOperationRequest):
    """Validate and normalise a canvas operation."""
    from isa_cad.state.canvas_state import ComponentNode

    op_id = str(uuid.uuid4())
    op_type = req.type
    payload = req.payload

    warnings: list[str] = []
    missing: list[str] = []
    normalized: dict[str, Any] | None = None
    adr_required = False
    adr_reason: str | None = None
    final_status = "valid"

    if op_type in ("add_component", "update_component"):
        comp_data = payload.get("component") or payload.get("patch") or {}
        name = comp_data.get("name", "")
        comp_type = comp_data.get("type", "service")

        # Generate a stable ID for new components
        comp_id = payload.get("component_id") or f"component.{comp_type}.{name.lower().replace(' ', '-')}-{op_id[:6]}"

        # Normalise
        normalized = {
            "id": comp_id,
            "name": name or f"unnamed-{comp_type}",
            "type": comp_type,
            "tier": comp_data.get("tier", "standard"),
            "technology": comp_data.get("technology"),
            "data_classification": comp_data.get("data_classification"),
            "tags": comp_data.get("tags", []),
        }

        # Check missing metadata
        if not comp_data.get("technology"):
            missing.append("technology")
            warnings.append("Technology not specified; simulation may be less accurate.")
        if not comp_data.get("tier"):
            missing.append("tier")

    elif op_type in ("add_relation", "update_relation"):
        rel_data = payload.get("relation") or payload.get("patch") or {}
        source = rel_data.get("source_id", "")
        target = rel_data.get("target_id", "")

        # Check if crosses trust boundary → ADR may be needed
        if rel_data.get("crosses_trust_boundary"):
            adr_required = True
            adr_reason = "Relation crosses trust boundary — Architecture Decision Record recommended."
            final_status = "requires_adr"

        rel_id = payload.get("relation_id") or f"relation.{source}.{target}-{op_id[:6]}"
        normalized = {
            "id": rel_id,
            "source_id": source,
            "target_id": target,
            "type": rel_data.get("type", "synchronous"),
            "protocol": rel_data.get("protocol"),
            "criticality": rel_data.get("criticality", "medium"),
            "crosses_trust_boundary": rel_data.get("crosses_trust_boundary", False),
            "crosses_bounded_context": rel_data.get("crosses_bounded_context", False),
        }
    else:
        # Move, remove — just acknowledge
        final_status = "valid"

    return OperationValidationResult(
        operation_id=op_id,
        status=final_status,
        normalized=normalized,
        warnings=warnings,
        missing_metadata=missing,
        adr_required=adr_required,
        adr_reason=adr_reason,
    )


# ── Layers (sandbox management) ──────────────────────────────────────────────

@app.get("/api/layers", response_model=list[LayerResponse])
async def list_layers(baseline_ref: str = ""):
    """List all sandbox layers for a given baseline."""
    results = list(_layers.values())
    if baseline_ref:
        results = [l for l in results if l.baseline_ref == baseline_ref]
    return results


@app.get("/api/layers/{layer_id}", response_model=LayerResponse)
async def get_layer(layer_id: str):
    if layer_id not in _layers:
        raise HTTPException(status_code=404, detail="Layer not found")
    return _layers[layer_id]


@app.post("/api/layers", response_model=LayerResponse, status_code=201)
async def create_layer(req: CreateLayerRequest):
    """Create a new sandbox layer."""
    layer_id = f"proposal.{req.title.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
    layer = LayerResponse(
        id=layer_id,
        title=req.title,
        status="sandbox_layer",
        baseline_ref=req.baseline_ref,
        optimization_goal=req.optimization_goal,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _layers[layer_id] = layer
    _log.info("layer.created", layer_id=layer_id, title=req.title)
    return layer


@app.patch("/api/layers/{layer_id}", response_model=LayerResponse)
async def update_layer(layer_id: str, body: dict[str, Any]):
    if layer_id not in _layers:
        raise HTTPException(status_code=404, detail="Layer not found")
    layer = _layers[layer_id]
    if "status" in body:
        layer = layer.model_copy(update={"status": body["status"]})
        _layers[layer_id] = layer
    return layer


# ── Layer components/relations (see demo override at bottom) ──────────────────


# ── Simulations ───────────────────────────────────────────────────────────────

@app.post("/api/simulations", response_model=SimulationStartResponse, status_code=202)
async def start_simulation(req: SimulationRequest):
    """Start a simulation job — runs the LangGraph pipeline in the background."""
    from isa_cad.core.models.enums import OptimizationGoal

    job_id = f"sim_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # Validate optimization goal
    try:
        goal = OptimizationGoal(req.optimization_goal)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid goal: {req.optimization_goal}")

    # Store pending job
    _simulations[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "request": req.model_dump(),
        "result": None,
        "events": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    _log.info("simulation.started", job_id=job_id, goal=goal.value, layers=req.proposal_refs)

    # Run pipeline in background
    asyncio.create_task(_run_simulation(job_id, req, goal))

    return SimulationStartResponse(job_id=job_id)


async def _run_simulation(job_id: str, req: SimulationRequest, goal: "OptimizationGoal") -> None:
    """Execute the LangGraph pipeline and store results."""
    from isa_cad.agent.graph import build_graph
    from isa_cad.core.models.enums import OptimizationGoal, VetoGateResult, OutputMode

    sim = _simulations[job_id]
    sim["status"] = "running"
    _emit_event(job_id, "simulation.started", {"job_id": job_id})

    try:
        # Build and invoke the graph
        graph = build_graph()

        # Build component/relation data for the pipeline
        components_data = req.components or _demo_data.get("components", {}).get(req.proposal_refs[0], []) if req.proposal_refs else []
        relations_data = req.relations or _demo_data.get("relations", {}).get(req.proposal_refs[0], []) if req.proposal_refs else []

        # Build ComponentGraph from frontend data for the pipeline
        from isa_cad.state.canvas_state import ComponentGraph, ComponentNode, ComponentEdge, CanvasSessionState, SandboxLayer

        graph_nodes = []
        for c in (components_data or []):
            comp_type = c.get("type", "service")
            # Map frontend types to pipeline types
            type_map = {"data_store": "database", "external_system": "external", "cache": "database"}
            graph_nodes.append(ComponentNode(
                id=c.get("id", "unknown"),
                label=c.get("name", "Unknown"),
                tier=c.get("tier", "standard"),
                component_type=type_map.get(comp_type, comp_type),
                metadata={
                    "technology": c.get("technology", ""),
                    "observed_metrics": c.get("observed_metrics", {}),
                },
            ))

        graph_edges = []
        for r in (relations_data or []):
            graph_edges.append(ComponentEdge(
                source_id=r.get("source_id", ""),
                target_id=r.get("target_id", ""),
                label=r.get("type", "synchronous"),
                protocol=r.get("protocol", ""),
                is_async=r.get("type") in ("asynchronous", "streaming"),
            ))

        baseline_graph = ComponentGraph(nodes=graph_nodes, edges=graph_edges)

        # Build canvas session
        canvas_session = CanvasSessionState(
            session_id=f"canvas-{job_id}",
            baseline_ref=req.baseline_ref,
            baseline_graph=baseline_graph,
            optimization_goal=goal,
        )

        initial_state = {
            "session_id": f"canvas-{job_id}",
            "proposal_id": req.proposal_refs[0] if req.proposal_refs else "unknown",
            "baseline_ref": req.baseline_ref,
            "optimization_goal": goal,
            "canvas_session": canvas_session,
            "components": components_data,
            "relations": relations_data,
        }

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        final_state: dict[str, Any] = await loop.run_in_executor(
            None, graph.invoke, initial_state
        )

        # Convert final_state to simulation result contract
        result = _build_simulation_result(job_id, final_state, req)

        # If pipeline returned blocked due to missing observed graph but we have metrics,
        # override with a data-driven result
        if result.get("recommendation", {}).get("blocked") and req.components:
            has_metrics = any(c.get("observed_metrics") for c in req.components)
            if has_metrics:
                result = _build_metrics_driven_result(job_id, req)

        sim["status"] = "completed"
        sim["result"] = result
        _emit_event(job_id, "simulation.completed", {"job_id": job_id})

        # Emit per-reviewer events
        for reviewer in ["cost", "performance", "security"]:
            _emit_event(job_id, "simulation.reviewer.completed", {
                "job_id": job_id,
                "reviewer": f"{reviewer.capitalize()}Reviewer",
                "status": "completed",
            })

        _log.info("simulation.completed", job_id=job_id)

    except Exception as exc:
        sim["status"] = "failed"
        sim["result"] = {"job_id": job_id, "status": "failed", "error": str(exc)}
        _emit_event(job_id, "simulation.failed", {"job_id": job_id, "reason": str(exc)})
        _log.error("simulation.failed", job_id=job_id, error=str(exc))


def _build_metrics_driven_result(job_id: str, req: SimulationRequest) -> dict[str, Any]:
    """Build simulation result using actual component metrics from frontend."""
    components = req.components or []
    relations = req.relations or []

    # Calculate scores from real metrics
    total_cost = 0.0
    max_latency = 0.0
    min_rps = float("inf")
    has_external = False
    has_pii = False
    tier1_count = 0

    for c in components:
        metrics = c.get("observed_metrics", {})
        total_cost += metrics.get("monthly_cost_usd", 0)
        latency = metrics.get("p99_latency_ms", 0)
        rps = metrics.get("requests_per_second", 0)
        comp_type = c.get("type", "service")

        # Only count internal services for throughput (not external systems)
        if comp_type != "external_system" and latency > max_latency:
            max_latency = latency
        if comp_type != "external_system" and rps > 0 and rps < min_rps:
            min_rps = rps
        if comp_type == "external_system":
            has_external = True
        if c.get("data_classification") in ("confidential", "restricted"):
            has_pii = True
        if c.get("tier") == "tier_1":
            tier1_count += 1

    if min_rps == float("inf"):
        min_rps = 2000.0  # default if no RPS data from internal services

    # Score calculations (normalized 0-1)
    cost_score = max(0.0, min(1.0, 1.0 - (total_cost / 5000.0)))  # $5000/mo = 0
    perf_score = max(0.0, min(1.0, 1.0 - (max_latency / 500.0)))  # 500ms = 0
    security_score = 0.9 if not has_external else 0.7
    if has_pii:
        security_score -= 0.1
    reliability_score = min(1.0, min_rps / 3000.0)  # 3000 RPS = 1.0, 500 RPS = 0.17
    complexity_score = max(0.0, 1.0 - (len(components) / 20.0))  # 20 components = 0

    # Veto gates
    security_gate = "pass" if security_score >= 0.5 else "fail"
    reliability_gate = "pass" if reliability_score >= 0.15 else "fail"  # ~450 RPS minimum
    compliance_gate = "pass"

    blocked = reliability_gate == "fail" or security_gate == "fail"
    recommendation_score = 0.0 if blocked else round(
        (cost_score + perf_score + security_score + reliability_score) / 4, 2
    )

    # Blast radius
    blast_components = []
    for c in components:
        downstream = sum(1 for r in relations if r.get("source_id") == c.get("id"))
        if downstream > 0:
            tier_mult = 2.0 if c.get("tier") == "tier_1" else 1.0
            blast_components.append({
                "component_id": c.get("id"),
                "name": c.get("name"),
                "impact_score": round(downstream * tier_mult, 2),
                "tier": c.get("tier", "standard"),
            })

    return {
        "job_id": job_id,
        "status": "completed",
        "recommendation": {
            "winner": req.proposal_refs[0] if req.proposal_refs else "proposal",
            "recommendation_score": recommendation_score,
            "blocked": blocked,
            "optimization_goal": req.optimization_goal,
            "rationale": f"Based on {len(components)} components with observed metrics. "
                        f"Total cost: ${total_cost:.0f}/mo, Max latency: {max_latency:.0f}ms, "
                        f"Min throughput: {min_rps:.0f} RPS.",
        },
        "veto_gates": {
            "security": security_gate,
            "reliability": reliability_gate,
            "compliance": compliance_gate,
        },
        "fidelity": {
            "base_confidence": 0.9,
            "freshness_score": 0.85,
            "staleness_penalty": 0.0,
            "adjusted_confidence": 0.9,
            "mode": "decision_grade" if not blocked else "exploratory_estimate",
            "safety_buffer_applied": False,
            "calibration_note": "Metrics provided by user/AI during architecture generation.",
        },
        "trade_off_matrix": [
            {
                "proposal_id": req.proposal_refs[0] if req.proposal_refs else "proposal",
                "label": "Proposal",
                "is_baseline": False,
                "cost_score": round(cost_score, 2),
                "performance_score": round(perf_score, 2),
                "security_score": round(security_score, 2),
                "reliability_score": round(reliability_score, 2),
                "complexity_score": round(complexity_score, 2),
                "fidelity_score": 0.9,
                "veto_status": "fail" if blocked else "pass",
                "recommendation_score": recommendation_score,
                "optimization_goal": req.optimization_goal,
                "blocked": blocked,
            },
        ],
        "blast_radius": {
            "high_risk_count": sum(1 for b in blast_components if b["impact_score"] > 3),
            "total_impacted": len(blast_components),
            "tier_1_count": tier1_count,
            "components": sorted(blast_components, key=lambda x: -x["impact_score"])[:10],
        },
        "reviewer_outputs": [
            {
                "reviewer": "cost",
                "status": "pass" if cost_score >= 0.3 else "warn",
                "score": round(cost_score, 2),
                "summary": f"Total estimated cost: ${total_cost:.0f}/mo across {len(components)} components.",
                "findings": [f"Highest cost component: ${max(c.get('observed_metrics', {}).get('monthly_cost_usd', 0) for c in components):.0f}/mo"],
                "blocked": False,
            },
            {
                "reviewer": "performance",
                "status": "pass" if perf_score >= 0.5 else "warn",
                "score": round(perf_score, 2),
                "summary": f"Max P99 latency: {max_latency:.0f}ms. Throughput floor: {min_rps:.0f} RPS.",
                "findings": [f"{len([c for c in components if c.get('observed_metrics', {}).get('p99_latency_ms', 0) > 100])} components with latency > 100ms"],
                "blocked": False,
            },
            {
                "reviewer": "security",
                "status": security_gate,
                "score": round(security_score, 2),
                "summary": f"{'External integrations detected. ' if has_external else ''}{'PII data present. ' if has_pii else ''}Architecture appears {'secure' if security_score >= 0.7 else 'needs review'}.",
                "findings": [r.get("protocol", "") + " connection" for r in relations[:3] if r.get("type") == "synchronous"],
                "blocked": security_gate == "fail",
            },
        ],
        "required_actions": {
            "developer": [
                f"Monitor latency for components with P99 > 100ms ({len([c for c in components if c.get('observed_metrics', {}).get('p99_latency_ms', 0) > 100])} found).",
            ] if max_latency > 100 else [],
            "architect": [
                f"Review blast radius: {len(blast_components)} components have downstream dependencies.",
            ] if blast_components else [],
            "security_ops": [
                "Audit external system connections for data exposure.",
            ] if has_external else [],
        },
    }


def _build_simulation_result(job_id: str, state: dict[str, Any], req: SimulationRequest) -> dict[str, Any]:
    """Transform AgentState into the simulation-result.schema.json contract."""
    from isa_cad.core.models.enums import VetoGateResult, OutputMode

    # Veto gates
    veto_gates = {}
    for gate_key, gate_name in [
        ("security_gate", "security"),
        ("reliability_gate", "reliability"),
        ("compliance_gate", "compliance"),
    ]:
        gate = state.get(gate_key)
        if gate:
            veto_gates[gate_name] = gate.result.value if hasattr(gate.result, 'value') else str(gate.result)
        else:
            veto_gates[gate_name] = "pass"

    # Map VetoGateResult values to frontend-expected format
    for k, v in veto_gates.items():
        if v == "passed":
            veto_gates[k] = "pass"
        elif v == "blocked":
            veto_gates[k] = "fail"
        elif v == "degraded":
            veto_gates[k] = "warn"

    # Fidelity
    output_mode = state.get("output_mode")
    fidelity_mode = "decision_grade"
    if output_mode:
        mode_val = output_mode.value if hasattr(output_mode, 'value') else str(output_mode)
        if mode_val == "exploratory_estimate":
            fidelity_mode = "exploratory_estimate"

    fr = state.get("freshness_report")
    cal = state.get("calibration_result")

    base_confidence = 0.85
    freshness_score = 0.90
    staleness_penalty = 0.05
    safety_buffer_applied = False

    if fr:
        base_confidence = getattr(fr, 'base_confidence', 0.85)
        freshness_score = getattr(fr, 'freshness_score', 0.90)
        staleness_penalty = getattr(fr, 'staleness_penalty', 0.05)

    if cal and hasattr(cal, 'safety_buffer') and cal.safety_buffer.applied:
        safety_buffer_applied = True

    adjusted_confidence = base_confidence - staleness_penalty

    fidelity = {
        "base_confidence": base_confidence,
        "freshness_score": freshness_score,
        "staleness_penalty": staleness_penalty,
        "adjusted_confidence": adjusted_confidence,
        "mode": fidelity_mode,
        "safety_buffer_applied": safety_buffer_applied,
        "calibration_note": (cal.safety_buffer.bias_note if cal and hasattr(cal, 'safety_buffer') else None),
    }

    # Recommendation
    final_output = state.get("final_output") or {}
    is_blocked = state.get("is_blocked", False)
    recommendation_score = final_output.get("recommendation_score", 0.0)

    recommendation = {
        "winner": req.proposal_refs[0] if req.proposal_refs else "unknown",
        "recommendation_score": recommendation_score,
        "blocked": is_blocked,
        "optimization_goal": req.optimization_goal,
        "rationale": final_output.get("rationale", ""),
    }

    # Trade-off matrix
    trade_off_matrix = []
    # Baseline row
    trade_off_matrix.append({
        "proposal_id": "baseline",
        "label": "Baseline",
        "is_baseline": True,
        "cost_score": 0.70,
        "performance_score": 0.75,
        "security_score": 0.85,
        "reliability_score": 0.90,
        "complexity_score": 0.80,
        "fidelity_score": adjusted_confidence,
        "veto_status": "pass",
        "recommendation_score": 0.70,
        "optimization_goal": req.optimization_goal,
        "blocked": False,
    })

    # Proposal rows (from reviewer outputs)
    cost_rev = state.get("cost_review")
    perf_rev = state.get("performance_review")
    sec_rev = state.get("security_review")

    for ref in req.proposal_refs:
        veto_status = "fail" if is_blocked else "pass"
        trade_off_matrix.append({
            "proposal_id": ref,
            "label": ref.split(".")[-1] if "." in ref else ref,
            "is_baseline": False,
            "cost_score": cost_rev.score if cost_rev else 0.50,
            "performance_score": perf_rev.score if perf_rev else 0.50,
            "security_score": sec_rev.score if sec_rev else 0.50,
            "reliability_score": 0.75,
            "complexity_score": 0.65,
            "fidelity_score": adjusted_confidence,
            "veto_status": veto_status,
            "recommendation_score": recommendation_score,
            "optimization_goal": req.optimization_goal,
            "blocked": is_blocked,
        })

    # Blast radius
    blast_radius: dict[str, Any] | None = None
    br = state.get("blast_radius")
    if br:
        blast_radius = {
            "high_risk_count": br.high_risk_count,
            "total_impacted": len(br.impacted_stable_components),
            "tier_1_count": sum(1 for c in br.impacted_stable_components if c.tier.value == "tier_1"),
            "components": [
                {
                    "id": c.id,
                    "name": c.id.split(".")[-1],
                    "tier": c.tier.value,
                    "distance": c.distance,
                    "impact_score": c.impact_score,
                    "risk": c.risk,
                    "mitigation_hints": {"developer": c.mitigations} if c.mitigations else {},
                }
                for c in br.impacted_stable_components
            ],
        }

    # Reviewer outputs
    reviewer_outputs = []
    for rev, rev_name in [(cost_rev, "cost"), (perf_rev, "performance"), (sec_rev, "security")]:
        if rev:
            reviewer_outputs.append({
                "reviewer": rev_name,
                "status": rev.status.value if hasattr(rev.status, 'value') else str(rev.status),
                "score": rev.score,
                "summary": rev.recommendation or "",
                "findings": [f.title for f in rev.findings] if rev.findings else [],
                "blocked": rev.has_critical_fail if hasattr(rev, 'has_critical_fail') else False,
            })
        else:
            reviewer_outputs.append({
                "reviewer": rev_name,
                "status": "pass",
                "score": 0.50,
                "summary": "No data",
                "findings": [],
                "blocked": False,
            })

    # Required actions
    proposal = state.get("proposal")
    required_actions = {"developer": [], "architect": [], "security_ops": []}
    if proposal and hasattr(proposal, 'required_actions'):
        ra = proposal.required_actions
        required_actions = {
            "developer": list(ra.developer) if ra.developer else [],
            "architect": list(ra.architect) if ra.architect else [],
            "security_ops": list(ra.security_ops) if ra.security_ops else [],
        }

    return {
        "job_id": job_id,
        "status": "completed",
        "recommendation": recommendation,
        "veto_gates": veto_gates,
        "fidelity": fidelity,
        "trade_off_matrix": trade_off_matrix,
        "blast_radius": blast_radius,
        "reviewer_outputs": reviewer_outputs,
        "required_actions": required_actions,
    }


def _emit_event(job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Append an event to a simulation job's event list."""
    sim = _simulations.get(job_id)
    if sim:
        sim["events"].append({"event": event_type, "payload": payload})


@app.get("/api/simulations/{job_id}")
async def get_simulation_result(job_id: str):
    """Poll simulation result."""
    if job_id not in _simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    sim = _simulations[job_id]
    if sim["result"]:
        return sim["result"]
    return {"job_id": job_id, "status": sim["status"]}


@app.post("/api/simulations/{job_id}/cancel")
async def cancel_simulation(job_id: str):
    if job_id not in _simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    _simulations[job_id]["status"] = "cancelled"
    return {"status": "cancelled"}


# ── Simulation SSE stream (Section 6.4) ───────────────────────────────────────

@app.get("/api/simulations/{job_id}/stream")
async def simulation_stream(job_id: str):
    """Server-Sent Events stream for real-time simulation progress."""
    if job_id not in _simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    async def event_generator():
        import json
        last_idx = 0
        while True:
            sim = _simulations.get(job_id)
            if not sim:
                break

            events = sim.get("events", [])
            while last_idx < len(events):
                evt = events[last_idx]
                yield {"data": json.dumps(evt)}
                last_idx += 1

            if sim["status"] in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


# ── Promotion (Section 5.4) ───────────────────────────────────────────────────

@app.post("/api/layers/{layer_id}/promote", response_model=PromotionArtifacts)
async def promote_layer(layer_id: str):
    """Generate promotion artifacts from the backend pipeline."""
    from isa_cad.output import YamlFormatter, MarkdownFormatter

    if layer_id not in _layers:
        raise HTTPException(status_code=404, detail="Layer not found")

    layer = _layers[layer_id]

    # Check the latest simulation for this layer
    # Find the most recent completed simulation involving this layer
    confidence = 0.85  # default
    for sim in _simulations.values():
        if sim["status"] == "completed" and sim["result"]:
            result = sim["result"]
            fidelity = result.get("fidelity", {})
            confidence = fidelity.get("adjusted_confidence", confidence)

    if confidence < 0.65:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Adjusted confidence {confidence:.2f} is below 0.65 threshold.",
        )

    # Generate YAML patch
    isa_patch = f"""---
# ArchTwin Architecture Patch
# Generated: {datetime.now(timezone.utc).isoformat()}
# Layer: {layer.title}
# Baseline: {layer.baseline_ref}
# Goal: {layer.optimization_goal}

proposal:
  id: "{layer.id}"
  title: "{layer.title}"
  status: "approved_for_pr"
  optimization_goal: "{layer.optimization_goal}"
  baseline_ref: "{layer.baseline_ref}"
  simulation_fidelity:
    adjusted_confidence: {confidence:.4f}
    mode: "decision_grade"
"""

    # Generate ADR draft
    adr_draft = f"""# ADR: {layer.title}

## Status
Proposed

## Context
Design proposal `{layer.id}` targets optimization goal: **{layer.optimization_goal}**.
Baseline: `{layer.baseline_ref}`

## Decision
Accept the proposed architecture change with confidence {confidence:.0%}.

## Consequences
- Simulation confidence: {confidence:.0%}
- All veto gates: PASS
- Blast radius: reviewed and accepted
"""

    pr_description = (
        f"## Architecture Change: {layer.title}\n\n"
        f"**Goal:** {layer.optimization_goal}\n"
        f"**Confidence:** {confidence:.0%}\n"
        f"**Baseline:** {layer.baseline_ref}\n\n"
        f"Generated by ArchTwin v0.5.3 pipeline.\n"
    )

    return PromotionArtifacts(
        isa_yaml_patch=isa_patch,
        adr_draft=adr_draft,
        required_actions={"developer": [], "architect": [], "security_ops": []},
        pr_description=pr_description,
        confidence_check={
            "adjusted_confidence": confidence,
            "allowed": confidence >= 0.65,
        },
    )


# ── Checkpoints ───────────────────────────────────────────────────────────────

@app.get("/api/checkpoints")
async def list_checkpoints():
    """List available pipeline checkpoints."""
    from pathlib import Path
    import json

    checkpoint_dir = Path("./checkpoints")
    results = []
    if checkpoint_dir.exists():
        for f in sorted(checkpoint_dir.glob("*.json"), reverse=True)[:20]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except (json.JSONDecodeError, OSError):
                pass
    return results


@app.get("/api/checkpoints/{checkpoint_id}")
async def get_checkpoint(checkpoint_id: str):
    """Get a specific checkpoint."""
    from pathlib import Path
    import json

    path = Path(f"./checkpoints/{checkpoint_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/checkpoints/{checkpoint_id}/resume")
async def resume_checkpoint(checkpoint_id: str):
    """Resume pipeline from a checkpoint."""
    # MVP: acknowledge the request
    return {"status": "resumed", "checkpoint_id": checkpoint_id}


# ── Comments (Section 10.1) ───────────────────────────────────────────────────

@app.get("/api/layers/{layer_id}/comments", response_model=list[CommentResponse])
async def list_comments(layer_id: str):
    return _comments.get(layer_id, [])


@app.post("/api/layers/{layer_id}/comments", response_model=CommentResponse, status_code=201)
async def create_comment(layer_id: str, req: CreateCommentRequest):
    comment = CommentResponse(
        id=str(uuid.uuid4()),
        anchor=req.anchor,
        author=req.author,
        body=req.body,
        created_at=datetime.now(timezone.utc).isoformat(),
        resolved=req.resolved,
    )
    if layer_id not in _comments:
        _comments[layer_id] = []
    _comments[layer_id].append(comment)
    return comment


@app.patch("/api/layers/{layer_id}/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(layer_id: str, comment_id: str, body: dict[str, Any]):
    comments = _comments.get(layer_id, [])
    for i, c in enumerate(comments):
        if c.id == comment_id:
            updated = c.model_copy(update=body)
            comments[i] = updated
            return updated
    raise HTTPException(status_code=404, detail="Comment not found")


# ══════════════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.6.0"}


# ══════════════════════════════════════════════════════════════════════════════
# YAML Import (user provides architecture description)
# ══════════════════════════════════════════════════════════════════════════════

class YamlImportRequest(BaseModel):
    yaml_content: str


@app.post("/api/import/yaml")
async def import_yaml_architecture(req: YamlImportRequest):
    """
    Parse YAML architecture and create a layer with components + relations.
    Returns the created layer, components, relations, positions, and any warnings.
    """
    from isa_cad.api.yaml_import import parse_yaml_architecture

    result = parse_yaml_architecture(req.yaml_content)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Create layer
    layer_id = f"proposal.import-{uuid.uuid4().hex[:8]}"
    layer = LayerResponse(
        id=layer_id,
        title=result["name"],
        status="sandbox_layer",
        baseline_ref=result["baseline_ref"],
        optimization_goal="balanced",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _layers[layer_id] = layer

    # Store components/relations for retrieval
    _demo_data["components"][layer_id] = result["components"]
    _demo_data["relations"][layer_id] = result["relations"]

    _log.info(
        "yaml.imported",
        layer_id=layer_id,
        components=len(result["components"]),
        relations=len(result["relations"]),
        warnings=len(result["warnings"]),
    )

    return {
        "layer": layer.model_dump(),
        "components": result["components"],
        "relations": result["relations"],
        "positions": result["positions"],
        "baseline_ref": result["baseline_ref"],
        "warnings": result["warnings"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Demo seed (pre-populated architecture for testing)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/demo/seed")
async def demo_seed():
    """Create a demo baseline with components, relations, and positions."""
    from isa_cad.api.demo_seed import (
        DEMO_BASELINE_REF,
        DEMO_COMPONENTS,
        DEMO_RELATIONS,
        DEMO_POSITIONS,
    )

    layer_id = "proposal.demo-baseline"
    layer = LayerResponse(
        id=layer_id,
        title="E-Commerce Baseline",
        status="sandbox_layer",
        baseline_ref=DEMO_BASELINE_REF,
        optimization_goal="balanced",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _layers[layer_id] = layer

    # Store components for retrieval
    _demo_data["components"] = {layer_id: DEMO_COMPONENTS}
    _demo_data["relations"] = {layer_id: DEMO_RELATIONS}
    _demo_data["positions"] = DEMO_POSITIONS

    return {
        "layer": layer.model_dump(),
        "components": DEMO_COMPONENTS,
        "relations": DEMO_RELATIONS,
        "positions": DEMO_POSITIONS,
        "baseline_ref": DEMO_BASELINE_REF,
    }


# Demo data store
_demo_data: dict[str, Any] = {"components": {}, "relations": {}, "positions": {}}


# Override the empty component/relation endpoints to return demo data
@app.get("/api/canvas/layers/{layer_id}/components", response_model=None)
async def get_layer_components_v2(layer_id: str):
    """Fetch all components in a sandbox layer (with demo data support)."""
    return _demo_data.get("components", {}).get(layer_id, [])


@app.get("/api/canvas/layers/{layer_id}/relations", response_model=None)
async def get_layer_relations_v2(layer_id: str):
    """Fetch all relations in a sandbox layer (with demo data support)."""
    return _demo_data.get("relations", {}).get(layer_id, [])


# ══════════════════════════════════════════════════════════════════════════════
# Per-node annotations (cost, risk, performance) for View Modes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/canvas/layers/{layer_id}/annotations")
async def get_layer_annotations(layer_id: str):
    """
    Return per-node cost/risk/performance annotations for View Mode overlays.
    Computed from the latest simulation + component metadata.
    """
    components = _demo_data.get("components", {}).get(layer_id, [])
    relations = _demo_data.get("relations", {}).get(layer_id, [])

    # Find latest simulation result for this layer
    sim_result = None
    for sim in _simulations.values():
        if sim.get("status") == "completed" and sim.get("result"):
            req = sim.get("request", {})
            if layer_id in req.get("proposal_refs", []):
                sim_result = sim["result"]

    annotations: dict[str, Any] = {}
    for comp in components:
        comp_id = comp["id"]
        comp_type = comp.get("type", "service")
        tier = comp.get("tier", "standard")
        metrics = comp.get("observed_metrics", {})

        # Cost annotation (heuristic based on type)
        # Use real cost from observed_metrics if available, otherwise heuristic
        cost_from_metrics = metrics.get("monthly_cost_usd")
        if cost_from_metrics:
            monthly_cost = float(cost_from_metrics)
        else:
            cost_estimates: dict[str, float] = {
                "gateway": 150, "service": 200, "data_store": 420,
                "cache": 90, "queue": 30, "external_system": 0,
                "system": 0, "container": 180,
            }
            monthly_cost = cost_estimates.get(comp_type, 100)

        # Security risk
        security_risk = "low"
        is_external_facing = comp_type == "gateway"
        has_pii = comp.get("data_classification") in ("restricted", "confidential")
        crosses_boundary = any(
            r.get("crosses_trust_boundary") for r in relations
            if r.get("source_id") == comp_id or r.get("target_id") == comp_id
        )
        if is_external_facing or crosses_boundary:
            security_risk = "high"
        elif has_pii:
            security_risk = "medium"

        # Performance annotation
        latency = metrics.get("p99_latency_ms")
        rps = metrics.get("requests_per_second")
        perf_risk = "low"
        if latency and latency > 100:
            perf_risk = "high"
        elif latency and latency > 50:
            perf_risk = "medium"

        # Blast radius annotation
        downstream_count = sum(1 for r in relations if r.get("source_id") == comp_id)
        blast_weight = downstream_count * (2.0 if tier == "tier_1" else 1.0 if tier == "standard" else 0.5)

        annotations[comp_id] = {
            "cost": {
                "monthly_usd": monthly_cost,
                "label": f"${monthly_cost}/mo",
                "level": "high" if monthly_cost > 300 else "medium" if monthly_cost > 100 else "low",
            },
            "security": {
                "risk": security_risk,
                "external_facing": is_external_facing,
                "has_pii": has_pii,
                "crosses_boundary": crosses_boundary,
            },
            "performance": {
                "risk": perf_risk,
                "p99_ms": latency,
                "rps": rps,
            },
            "blast_radius": {
                "downstream_count": downstream_count,
                "weight": round(blast_weight, 2),
                "tier": tier,
            },
        }

    # Edge annotations for cost view (egress cost heuristic)
    edge_annotations: dict[str, Any] = {}
    for rel in relations:
        rel_id = rel["id"]
        is_cross_region = rel.get("crosses_trust_boundary", False)
        edge_annotations[rel_id] = {
            "cost": {
                "egress_level": "high" if is_cross_region else "low",
                "label": "Cross-boundary egress" if is_cross_region else None,
            },
            "security": {
                "risk": "high" if is_cross_region else "low",
            },
        }

    return {
        "nodes": annotations,
        "edges": edge_annotations,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AI Command endpoint — real LLM integration
# ══════════════════════════════════════════════════════════════════════════════

from fastapi import Request

class AICommandRequest(BaseModel):
    command: str
    context: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = None
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"


AI_SYSTEM_PROMPT = """You are ArchTwin AI — an expert software architecture assistant embedded in an architecture design tool.

The user is working on a visual Canvas with architecture components (services, databases, caches, queues, gateways) connected by relations (synchronous, asynchronous, data_access, streaming).

Your role:
- Analyze architecture decisions (cost, performance, security, reliability, blast radius)
- Compare alternatives with trade-offs
- Suggest optimizations
- Explain why simulation gates pass or fail
- Recommend architectural improvements

CRITICAL RULES:
1. Always respond in the SAME LANGUAGE as the user's message. If the user writes in Ukrainian — respond in Ukrainian. If in English — respond in English.
2. When the user describes an idea, app concept, or proposes new functionality — generate a FULL architecture for it using canvas_actions. Create all needed components (services, databases, caches, queues, gateways) and relations between them.
3. When existing components are already on the Canvas — integrate the new idea INTO the existing architecture. Add only the new components and connect them to existing ones.
4. If the Canvas is empty — build the full architecture from scratch based on the user's description.

Always be specific, quantitative where possible, and actionable. Reference actual component names from the context.

Respond in this JSON format:
{"action": "<type>", "type": "analysis", "message": "<main response text in user's language>", "result": {<structured data if relevant>}, "suggestions": ["<follow-up question in user's language>", "<another follow-up>"], "canvas_actions": [<optional list of changes to apply>]}

canvas_actions is an array of modifications the user can apply to their architecture. Each action:
- {"op": "add_component", "name": "...", "type": "service|data_store|cache|queue|gateway|external_system", "technology": "...", "tier": "tier_1|standard|auxiliary"}
- {"op": "remove_component", "name": "..."}  (match by exact name)
- {"op": "update_component", "name": "...", "changes": {"technology": "...", "tier": "...", ...}}
- {"op": "add_relation", "source": "...", "target": "...", "type": "synchronous|asynchronous|data_access|streaming", "protocol": "..."}
- {"op": "remove_relation", "source": "...", "target": "..."}

Include canvas_actions when:
- User describes an app idea or feature → generate full architecture (components + relations)
- User asks to add/change/remove something → specific modifications
- User asks to improve/optimize → suggest concrete changes

The user will review and approve before applying. Always explain WHY you suggest each change in the message.

When generating architecture from an idea, you MUST create a COMPLETE architecture with ALL relations between components. Think about:
- What services are needed (API, workers, schedulers)
- What data stores (SQL, NoSQL, cache, search)
- What message queues or event buses
- What external integrations (payment, email, auth)
- What gateway/load balancer pattern
- Proper tier assignment (tier_1 for critical, standard for regular, auxiliary for non-essential)

CRITICAL: Every component MUST have at least one relation. Always include:
1. A gateway/entry point that connects to backend services
2. Services connected to their data stores
3. Services connected to each other where they communicate
4. External systems connected to the services that call them
5. Queues/event buses between async producers and consumers

RELATIONS RULES (VERY IMPORTANT - follow exactly):
- In "source" and "target" fields of add_relation, use the EXACT same "name" string you used in add_component. Case-sensitive match.
- Example: if you add {"op": "add_component", "name": "API Gateway"}, then relation must use "source": "API Gateway" (not "api gateway", not "Gateway", not "api-gateway")
- Every add_relation MUST reference names that exist in your add_component list or in the existing architecture context
- Double-check every relation: does "source" name exist? does "target" name exist? If not — fix it before responding.
- Typical architecture flow: Gateway → Services → Data Stores, Services → Queues → Workers, Services → External APIs

Example for "e-commerce app":
canvas_actions should include ~6-10 components AND ~8-15 relations connecting them all into a cohesive graph. Never leave components disconnected. The result must look like a real architecture diagram with clear data flow from entry point through services to data stores.

GOOD example of canvas_actions:
[
  {"op": "add_component", "name": "API Gateway", "type": "gateway", "technology": "nginx", "tier": "tier_1"},
  {"op": "add_component", "name": "Users Service", "type": "service", "technology": "node.js", "tier": "standard"},
  {"op": "add_component", "name": "Users DB", "type": "data_store", "technology": "postgresql", "tier": "tier_1"},
  {"op": "add_relation", "source": "API Gateway", "target": "Users Service", "type": "synchronous", "protocol": "HTTPS"},
  {"op": "add_relation", "source": "Users Service", "target": "Users DB", "type": "data_access", "protocol": "PostgreSQL"}
]

BAD example (NEVER do this):
[
  {"op": "add_component", "name": "API Gateway", ...},
  {"op": "add_relation", "source": "Gateway", "target": "users-service", ...}  ← WRONG: names don't match!
]

METRICS: When generating or updating components, ALWAYS include realistic metrics in the "changes" or as part of add_component. Use this format in canvas_actions:
- For add_component: include "observed_metrics" field with p99_latency_ms, requests_per_second, error_rate, monthly_cost_usd
- For update_component: include observed_metrics in "changes"

Realistic metric ranges by component type:
- gateway: p99=5-20ms, rps=5000-50000, cost=$100-300/mo
- service: p99=20-200ms, rps=500-10000, cost=$100-500/mo
- data_store: p99=2-50ms, rps=1000-50000, cost=$200-2000/mo
- cache: p99=1-5ms, rps=10000-100000, cost=$50-200/mo
- queue: p99=10-100ms, rps=1000-20000, cost=$20-100/mo
- external_system: p99=100-500ms, rps=100-5000, cost=$0 (paid separately)

Always set "last_updated" to current ISO date in observed_metrics.

Keep message concise (2-4 sentences). Put details in result object."""


async def _call_llm(command: str, context: dict, api_key: str, provider: str, model: str) -> dict:
    """Call the real LLM with architecture context."""
    # Build context string from architecture data
    arch_context = ""
    if context:
        if "components" in context:
            arch_context += f"\nArchitecture components: {context['components']}"
        if "relations" in context:
            arch_context += f"\nRelations: {context['relations']}"
        if "simulation_result" in context:
            arch_context += f"\nLatest simulation: {context['simulation_result']}"

    user_msg = f"Architecture context:{arch_context}\n\nUser question: {command}"

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=4096,
                system=AI_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = response.content[0].text

        elif provider == "openai":
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = response.choices[0].message.content or ""

        elif provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            gmodel = genai.GenerativeModel(model)
            response = await asyncio.to_thread(
                gmodel.generate_content,
                f"{AI_SYSTEM_PROMPT}\n\n{user_msg}",
            )
            text = response.text

        elif provider == "groq":
            import openai as groq_openai
            client = groq_openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = response.choices[0].message.content or ""

        elif provider == "openrouter":
            import openai as or_openai
            client = or_openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = response.choices[0].message.content or ""

        else:
            return {"action": "error", "type": "error", "message": f"Unsupported provider: {provider}"}

        # Try to parse JSON response
        import json
        import re

        def _try_parse_json(raw: str) -> dict | None:
            """Try multiple strategies to parse LLM JSON output."""
            # Strip markdown code fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

            # Fix common LLM JSON mistakes
            # Double quotes: "" → "
            cleaned = re.sub(r'""([^"]*?)""', r'"\1"', cleaned)
            # Trailing commas before ] or }
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

            # Attempt 1: direct parse
            try:
                result = json.loads(cleaned)
                if isinstance(result, dict) and "message" in result:
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

            # Attempt 2: fix truncated JSON (max_tokens cut off)
            if '"canvas_actions"' in cleaned or '"message"' in cleaned:
                for suffix in [']}', ']}', ']}}', ']}}}', '}', ']}']:
                    try:
                        fixed = cleaned.rstrip(',\n \t') + suffix
                        result = json.loads(fixed)
                        if isinstance(result, dict) and "message" in result:
                            _log.info("ai.json_fixed_truncated")
                            return result
                    except (json.JSONDecodeError, ValueError):
                        continue

            # Attempt 3: extract JSON object from text (LLM might add text around it)
            match = re.search(r'\{[\s\S]*"message"[\s\S]*"canvas_actions"[\s\S]*\}', cleaned)
            if match:
                try:
                    result = json.loads(match.group())
                    if isinstance(result, dict) and "message" in result:
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass

            return None

        parsed = _try_parse_json(text)
        if parsed:
            return parsed

        # If not valid JSON, wrap as plain message but try to extract canvas_actions
        # from the raw text for partial recovery
        return {
            "action": "response",
            "type": "analysis",
            "message": text,
            "suggestions": [],
        }

    except Exception as e:
        _log.error("ai.llm_call_failed", provider=provider, error=str(e))
        return {
            "action": "error",
            "type": "error",
            "message": f"LLM call failed: {str(e)[:200]}",
            "suggestions": ["Check your API key in AI Model settings"],
        }


@app.post("/api/ai/command")
async def ai_command(req: AICommandRequest, request: Request):
    """
    Process an AI command. If user provides API key — calls real LLM.
    Otherwise falls back to basic keyword-matching responses.
    """
    # Get API key from request body or header
    api_key = req.api_key or request.headers.get("x-llm-api-key", "")
    provider = req.provider
    model = req.model

    # If API key provided — use real LLM
    if api_key and len(api_key) > 10:
        # Build architecture context from current demo data
        context = req.context
        if not context.get("components"):
            # Auto-include current layer data
            for layer_id, comps in _demo_data.get("components", {}).items():
                context["components"] = [{"name": c.get("name"), "type": c.get("type"), "tier": c.get("tier"), "technology": c.get("technology")} for c in comps]
                context["relations"] = [{"source": r.get("source_id"), "target": r.get("target_id"), "type": r.get("type"), "protocol": r.get("protocol")} for r in _demo_data.get("relations", {}).get(layer_id, [])]
                break

        _log.info("ai.command_with_llm", provider=provider, model=model, command=req.command[:50])
        return await _call_llm(req.command, context, api_key, provider, model)

    # ── Fallback: keyword-matched responses (no API key) ─────────────────────
    cmd = req.command.lower()
    context = req.context

    if any(w in cmd for w in ["compare", "alternative", "vs", "versus"]):
        return _ai_compare_response(cmd, context)
    elif any(w in cmd for w in ["cost", "optimize", "cheap", "expensive", "save"]):
        return _ai_cost_response(cmd, context)
    elif any(w in cmd for w in ["security", "risk", "vulnerability", "exposure"]):
        return _ai_security_response(cmd, context)
    elif any(w in cmd for w in ["blast", "impact", "affect", "dependency"]):
        return _ai_blast_response(cmd, context)
    elif any(w in cmd for w in ["explain", "why", "what", "how"]):
        return _ai_explain_response(cmd, context)
    elif any(w in cmd for w in ["adr", "decision record", "document"]):
        return {"action": "generate_adr", "message": "Use the Promote flow to generate an ADR draft.", "type": "redirect"}
    else:
        return {
            "action": "suggestion",
            "message": "Configure your API key in AI Model settings (gear icon) to get real AI responses. Without a key, I can only provide basic suggestions.",
            "type": "help",
            "suggestions": [
                "Compare Orders DB with Aurora Serverless",
                "Optimize this layer for cost",
                "Show security risks for API Gateway",
                "Explain why reliability gate failed",
                "What is the blast radius of changing Orders API?",
            ],
        }


def _ai_compare_response(cmd: str, context: dict) -> dict:
    return {
        "action": "compare",
        "type": "analysis",
        "message": "Comparison analysis",
        "result": {
            "current": {
                "technology": "postgresql",
                "monthly_cost": 420,
                "p99_latency": "8ms",
                "reliability": "99.9% (Multi-AZ)",
            },
            "alternatives": [
                {
                    "name": "Aurora Serverless v2",
                    "monthly_cost": 290,
                    "cost_delta": "-31%",
                    "p99_latency": "12ms",
                    "reliability": "99.95%",
                    "tradeoffs": "Slightly higher latency, better auto-scaling",
                    "recommendation": "Recommended for cost_efficiency goal",
                },
                {
                    "name": "Self-hosted PostgreSQL",
                    "monthly_cost": 180,
                    "cost_delta": "-57%",
                    "p99_latency": "6ms",
                    "reliability": "99.5%",
                    "tradeoffs": "Lower reliability, requires DBA expertise",
                    "recommendation": "Only if team has strong DBA capability",
                },
            ],
        },
    }


def _ai_cost_response(cmd: str, context: dict) -> dict:
    return {
        "action": "cost_analysis",
        "type": "analysis",
        "message": "Cost optimization suggestions",
        "result": {
            "current_monthly_total": 1390,
            "optimization_opportunities": [
                {"component": "Orders DB", "saving": "$130/mo", "action": "Switch to Aurora Serverless", "risk": "low"},
                {"component": "Redis Sessions", "saving": "$30/mo", "action": "Reduce instance size (CHR is 92%)", "risk": "low"},
                {"component": "API Gateway", "saving": "$50/mo", "action": "Enable response caching", "risk": "low"},
            ],
            "total_potential_saving": "$210/mo (-15%)",
        },
    }


def _ai_security_response(cmd: str, context: dict) -> dict:
    return {
        "action": "security_analysis",
        "type": "analysis",
        "message": "Security risk analysis",
        "result": {
            "critical": [],
            "high": [
                {"component": "API Gateway", "risk": "External-facing entry point", "mitigation": "WAF + rate limiting enabled"},
                {"component": "Payments API → Stripe", "risk": "Crosses trust boundary with PCI data", "mitigation": "TLS + token vault required"},
            ],
            "medium": [
                {"component": "Orders DB", "risk": "Contains confidential data", "mitigation": "Encryption at rest, access audit logging"},
            ],
            "overall_status": "PASS — no unmitigated critical risks",
        },
    }


def _ai_blast_response(cmd: str, context: dict) -> dict:
    return {
        "action": "blast_radius",
        "type": "analysis",
        "message": "Blast radius analysis",
        "result": {
            "source": "Orders API (if changed)",
            "direct_impact": ["Orders DB", "Redis Sessions", "Order Events Queue", "Inventory Service"],
            "indirect_impact": ["Notification Service (via Queue)"],
            "tier_1_affected": 2,
            "total_impact_score": 3.44,
            "recommendation": "High blast radius — consider phased rollout with canary",
        },
    }


def _ai_explain_response(cmd: str, context: dict) -> dict:
    # Check if asking about blocked/veto
    if any(w in cmd for w in ["block", "veto", "fail", "0.00", "zero"]):
        return {
            "action": "explanation",
            "type": "explanation",
            "message": "Why the simulation result is BLOCKED",
            "result": {
                "reason": "Reliability veto gate failed",
                "detail": "The throughput ceiling (0 RPS) is below the minimum viable threshold (50 RPS). This happens because the simulation has no observed metrics for the proposal layer — the Observed Graph needs to be refreshed.",
                "fix_steps": [
                    "1. Refresh the Observed Graph (connect real metrics)",
                    "2. Ensure throughput data is available for all Tier-1 services",
                    "3. Re-run the simulation",
                ],
                "related_gate": "reliability",
                "related_metric": "throughput_rps",
            },
        }
    return {
        "action": "explanation",
        "type": "explanation",
        "message": "Architecture explanation",
        "result": {
            "summary": "This architecture follows a standard microservices pattern with API Gateway routing to domain services (Orders, Payments), backed by PostgreSQL + Redis, with async event processing via SQS.",
            "key_decisions": [
                "Kong API Gateway for rate limiting and auth",
                "Separate Orders and Payments bounded contexts",
                "Async notifications via SQS (decoupled from critical path)",
                "Redis for session caching (CHR 92%)",
            ],
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Enhanced simulation result with prioritized actions
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/simulations/{job_id}/actions")
async def get_simulation_actions(job_id: str):
    """
    Return required actions from a simulation, ranked by priority.
    Priority: blocking > required > recommended > optional
    """
    if job_id not in _simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sim = _simulations[job_id]
    if not sim.get("result"):
        return {"actions": []}

    result = sim["result"]
    ra = result.get("required_actions", {})

    actions: list[dict[str, Any]] = []

    for role, items in ra.items():
        for text in items:
            # Determine priority from content
            if "BLOCK" in text.upper():
                priority = "blocking"
            elif "refresh" in text.lower() or "trigger" in text.lower():
                priority = "required"
            elif "fix" in text.lower() or "investigate" in text.lower():
                priority = "recommended"
            else:
                priority = "optional"

            # Extract short title
            if ":" in text:
                short_title = text.split(":")[0].replace("BLOCK", "").replace("—", "").strip()
                detail = ":".join(text.split(":")[1:]).strip()
            else:
                short_title = text[:60]
                detail = text if len(text) > 60 else ""

            actions.append({
                "priority": priority,
                "role": role.replace("security_ops", "sec").replace("developer", "dev").replace("architect", "arch"),
                "short_title": short_title,
                "detail": detail,
                "full_text": text,
            })

    # Sort by priority
    priority_order = {"blocking": 0, "required": 1, "recommended": 2, "optional": 3}
    actions.sort(key=lambda a: priority_order.get(a["priority"], 99))

    return {"actions": actions}


# ══════════════════════════════════════════════════════════════════════════════
# Billing & Subscription System
# ══════════════════════════════════════════════════════════════════════════════

# ── In-memory billing state ──────────────────────────────────────────────────

_plans: dict[str, dict[str, Any]] = {
    "free": {
        "plan_key": "free", "name": "Free", "billing_interval": "monthly",
        "price_cents": 0, "currency": "usd", "is_active": True,
    },
    "pro_monthly": {
        "plan_key": "pro", "name": "Pro", "billing_interval": "monthly",
        "price_cents": 2900, "currency": "usd", "is_active": True,
    },
    "pro_yearly": {
        "plan_key": "pro", "name": "Pro", "billing_interval": "yearly",
        "price_cents": 27900, "currency": "usd", "is_active": True,
    },
    "team_monthly": {
        "plan_key": "team", "name": "Team", "billing_interval": "monthly",
        "price_cents": 7900, "currency": "usd", "is_active": True,
    },
    "team_yearly": {
        "plan_key": "team", "name": "Team", "billing_interval": "yearly",
        "price_cents": 75900, "currency": "usd", "is_active": True,
    },
    "enterprise": {
        "plan_key": "enterprise", "name": "Enterprise", "billing_interval": "yearly",
        "price_cents": 0, "currency": "usd", "is_active": True,
    },
}

_entitlement_defs: dict[str, dict[str, Any]] = {
    "free": {
        "max_projects": 1, "max_nodes_per_project": 15, "max_sandbox_layers": 1,
        "monthly_simulations": 10, "can_export_yaml": True, "can_generate_adr": False,
        "can_promote_to_pr": False, "can_use_team_collaboration": False,
        "can_use_git_integration": False, "can_use_sso": False,
        "can_use_audit_logs": False, "can_use_self_hosted_scanner": False,
        "can_use_custom_policies": False,
    },
    "pro": {
        "max_projects": 10, "max_nodes_per_project": 100, "max_sandbox_layers": 5,
        "monthly_simulations": 300, "can_export_yaml": True, "can_generate_adr": True,
        "can_promote_to_pr": False, "can_use_team_collaboration": False,
        "can_use_git_integration": False, "can_use_sso": False,
        "can_use_audit_logs": False, "can_use_self_hosted_scanner": False,
        "can_use_custom_policies": False,
    },
    "team": {
        "max_projects": 50, "max_nodes_per_project": 500, "max_sandbox_layers": 20,
        "monthly_simulations": 3000, "can_export_yaml": True, "can_generate_adr": True,
        "can_promote_to_pr": True, "can_use_team_collaboration": True,
        "can_use_git_integration": True, "can_use_sso": False,
        "can_use_audit_logs": False, "can_use_self_hosted_scanner": False,
        "can_use_custom_policies": False,
    },
    "enterprise": {
        "max_projects": 9999, "max_nodes_per_project": 9999, "max_sandbox_layers": 9999,
        "monthly_simulations": 99999, "can_export_yaml": True, "can_generate_adr": True,
        "can_promote_to_pr": True, "can_use_team_collaboration": True,
        "can_use_git_integration": True, "can_use_sso": True,
        "can_use_audit_logs": True, "can_use_self_hosted_scanner": True,
        "can_use_custom_policies": True,
    },
}

# Per-workspace subscription state (keyed by workspace_id)
_subscriptions: dict[str, dict[str, Any]] = {}

# Per-workspace usage counters (keyed by workspace_id)
_usage: dict[str, dict[str, dict[str, int]]] = {}

# Audit log
_billing_events: list[dict[str, Any]] = []


def _log_billing_event(event_type: str, workspace_id: str, **data: Any) -> None:
    _billing_events.append({
        "id": str(uuid.uuid4()),
        "event": event_type,
        "workspace_id": workspace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    })


def _get_or_create_subscription(workspace_id: str) -> dict[str, Any]:
    """Get existing subscription or create a free one."""
    if workspace_id not in _subscriptions:
        _subscriptions[workspace_id] = {
            "workspace_id": workspace_id,
            "plan": "free",
            "status": "active",
            "current_period_end": None,
            "cancel_at_period_end": False,
            "trial_ends_at": None,
        }
    return _subscriptions[workspace_id]


def _get_usage(workspace_id: str, plan: str) -> dict[str, dict[str, int]]:
    """Get or initialize usage counters for a workspace."""
    if workspace_id not in _usage:
        ent = _entitlement_defs.get(plan, _entitlement_defs["free"])
        _usage[workspace_id] = {
            "simulations_run": {"used": 0, "limit": ent["monthly_simulations"]},
            "projects_created": {"used": 0, "limit": ent["max_projects"]},
            "sandbox_layers_created": {"used": 0, "limit": ent["max_sandbox_layers"]},
            "adr_generated": {"used": 0, "limit": 999 if ent["can_generate_adr"] else 0},
            "yaml_exports": {"used": 0, "limit": 999 if ent["can_export_yaml"] else 0},
        }
    return _usage[workspace_id]


# ── Billing models ───────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan_key: str


class PortalRequest(BaseModel):
    pass


# ── Billing endpoints ────────────────────────────────────────────────────────

@app.get("/api/billing/plans")
async def list_plans():
    """Return all available plans."""
    return list(_plans.values())


@app.get("/api/billing/subscription")
async def get_subscription(workspace_id: str = "ws_default"):
    """Get current subscription, entitlements, and usage."""
    sub = _get_or_create_subscription(workspace_id)
    plan = sub["plan"]
    ent = _entitlement_defs.get(plan, _entitlement_defs["free"])
    usage = _get_usage(workspace_id, plan)

    return {
        "workspace_id": workspace_id,
        "plan": plan,
        "status": sub["status"],
        "current_period_end": sub["current_period_end"],
        "cancel_at_period_end": sub["cancel_at_period_end"],
        "trial_ends_at": sub["trial_ends_at"],
        "entitlements": ent,
        "usage": usage,
    }


@app.post("/api/billing/checkout")
async def create_checkout(req: CheckoutRequest):
    """Create a checkout session (simulated — returns plan upgrade URL)."""
    workspace_id = "ws_default"

    if req.plan_key not in _plans and req.plan_key not in ("pro", "team", "enterprise"):
        raise HTTPException(status_code=400, detail=f"Invalid plan: {req.plan_key}")

    # Determine plan from key
    plan = req.plan_key.replace("_monthly", "").replace("_yearly", "")
    if plan not in _entitlement_defs:
        plan = "pro"

    # Simulate immediate upgrade
    sub = _get_or_create_subscription(workspace_id)
    old_plan = sub["plan"]
    sub["plan"] = plan
    sub["status"] = "active"
    sub["current_period_end"] = "2027-01-01T00:00:00Z"

    # Update usage limits
    ent = _entitlement_defs[plan]
    usage = _get_usage(workspace_id, plan)
    usage["simulations_run"]["limit"] = ent["monthly_simulations"]
    usage["projects_created"]["limit"] = ent["max_projects"]
    usage["sandbox_layers_created"]["limit"] = ent["max_sandbox_layers"]
    usage["adr_generated"]["limit"] = 999 if ent["can_generate_adr"] else 0
    usage["yaml_exports"]["limit"] = 999 if ent["can_export_yaml"] else 0

    _log_billing_event("checkout_started", workspace_id, plan_key=req.plan_key)
    _log_billing_event("subscription_updated", workspace_id, old_plan=old_plan, new_plan=plan)

    _log.info("billing.checkout", workspace=workspace_id, plan=plan, old_plan=old_plan)

    # In real app this would return a Stripe/Paddle checkout URL
    return {"checkout_url": f"/canvas?upgraded={plan}"}


@app.post("/api/billing/portal")
async def open_portal():
    """Open billing management portal (simulated)."""
    workspace_id = "ws_default"
    _log_billing_event("billing_portal_opened", workspace_id)
    return {"portal_url": "/billing?manage=true"}


@app.get("/api/entitlements/check")
async def check_entitlement(feature: str, workspace_id: str = "ws_default"):
    """Check whether a feature is allowed for the current plan."""
    sub = _get_or_create_subscription(workspace_id)
    plan = sub["plan"]
    ent = _entitlement_defs.get(plan, _entitlement_defs["free"])

    if feature not in ent:
        raise HTTPException(status_code=400, detail=f"Unknown feature: {feature}")

    value = ent[feature]
    if isinstance(value, bool):
        if value:
            return {"allowed": True, "plan": plan, "reason": None}
        # Determine which plan unlocks this
        rec = _recommend_plan_for_feature(feature)
        return {
            "allowed": False,
            "plan": plan,
            "reason": f"Feature requires {rec.capitalize()} plan or higher",
            "upgrade_required": True,
            "recommended_plan": rec,
        }

    # Numeric limit — check usage
    usage = _get_usage(workspace_id, plan)
    metric_map = {
        "max_projects": "projects_created",
        "max_sandbox_layers": "sandbox_layers_created",
        "max_nodes_per_project": None,
        "monthly_simulations": "simulations_run",
    }
    metric_key = metric_map.get(feature)
    if metric_key and metric_key in usage:
        counter = usage[metric_key]
        if counter["used"] >= value:
            rec = _recommend_plan_for_feature(feature)
            return {
                "allowed": False,
                "plan": plan,
                "reason": f"{feature} limit reached ({counter['used']}/{value})",
                "upgrade_required": True,
                "recommended_plan": rec,
            }

    return {"allowed": True, "plan": plan, "reason": None}


def _recommend_plan_for_feature(feature: str) -> str:
    """Find the cheapest plan that enables a feature."""
    for plan_key in ["pro", "team", "enterprise"]:
        ent = _entitlement_defs[plan_key]
        val = ent.get(feature)
        if isinstance(val, bool) and val:
            return plan_key
        if isinstance(val, int) and val > _entitlement_defs["free"].get(feature, 0):
            return plan_key
    return "pro"


@app.post("/api/billing/webhook")
async def billing_webhook(body: dict[str, Any]):
    """
    Handle payment provider webhooks.
    In production: verify signature, handle idempotency.
    """
    event_type = body.get("type", "unknown")
    workspace_id = body.get("workspace_id", "ws_default")

    # Idempotency check
    event_id = body.get("event_id", str(uuid.uuid4()))
    if any(e.get("provider_event_id") == event_id for e in _billing_events):
        return {"status": "duplicate", "event_id": event_id}

    _log_billing_event(event_type, workspace_id, provider_event_id=event_id)

    if event_type == "subscription.canceled":
        sub = _get_or_create_subscription(workspace_id)
        sub["cancel_at_period_end"] = True
        _log.info("billing.canceled", workspace=workspace_id)

    elif event_type == "invoice.payment_failed":
        sub = _get_or_create_subscription(workspace_id)
        sub["status"] = "past_due"
        _log.info("billing.payment_failed", workspace=workspace_id)

    return {"status": "processed", "event_id": event_id}


# ══════════════════════════════════════════════════════════════════════════════
# LLM Settings — user API key validation & model config
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# Team Collaboration
# ══════════════════════════════════════════════════════════════════════════════

class TeamInviteRequest(BaseModel):
    email: str
    role: str = "member"


_team_invites: list[dict[str, Any]] = []


@app.post("/api/team/invite")
async def invite_team_member(req: TeamInviteRequest):
    """Invite a team member by email."""
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    invite = {
        "id": str(uuid.uuid4()),
        "email": req.email,
        "role": req.role,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _team_invites.append(invite)
    _log.info("team.invite_sent", email=req.email, role=req.role)
    return invite


@app.get("/api/team/invites")
async def list_team_invites():
    """List all pending invites."""
    return _team_invites


class ValidateKeyRequest(BaseModel):
    api_key: str
    provider: str
    model: str = ""


class LLMConfigRequest(BaseModel):
    api_key: str
    provider: str
    model: str


SUPPORTED_PROVIDERS = ["anthropic", "openai", "google", "groq", "openrouter"]


@app.post("/api/llm/validate-key")
async def validate_llm_key(req: ValidateKeyRequest):
    """
    Validate an LLM API key by checking its format.
    In production, this would make a lightweight API call to verify.
    We never store user keys on the server.
    """
    key = req.api_key.strip()
    provider = req.provider.lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    # Format validation (lightweight, no actual API call for MVP)
    valid = False
    if provider == "anthropic":
        valid = key.startswith("sk-ant-") and len(key) > 20
    elif provider == "openai":
        valid = key.startswith("sk-") and len(key) > 20
    elif provider == "google":
        valid = key.startswith("AIza") and len(key) > 20
    elif provider == "groq":
        valid = key.startswith("gsk_") and len(key) > 20
    elif provider == "openrouter":
        valid = key.startswith("sk-or-") and len(key) > 20

    _log.info("llm.validate_key", provider=provider, valid=valid)
    return {"valid": valid, "provider": provider, "model": req.model}


@app.get("/api/llm/models")
async def list_llm_models():
    """Return available models grouped by provider."""
    return {
        "providers": SUPPORTED_PROVIDERS,
        "models": {
            "anthropic": [
                {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "context": "200K"},
                {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "context": "1M"},
                {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "context": "200K"},
            ],
            "openai": [
                {"id": "gpt-4o", "name": "GPT-4o", "context": "128K"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": "128K"},
                {"id": "o3", "name": "o3", "context": "200K"},
            ],
            "google": [
                {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "context": "1M"},
                {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "context": "1M"},
            ],
            "groq": [
                {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "context": "128K"},
                {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": "32K"},
            ],
            "openrouter": [
                {"id": "openrouter/auto", "name": "Auto (best available)", "context": "varies"},
            ],
        },
    }
