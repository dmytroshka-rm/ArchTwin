from __future__ import annotations

"""
isa_cad/agent/graph.py
======================
LangGraph StateGraph wiring for the ISA-CAD agent pipeline.

Pipeline topology
-----------------
START
  └─► context_freshness
        └─► build_design_delta
              └─► parallel_reviewer          (ThreadPoolExecutor inside node)
                    ├─► security_veto
                    ├─► reliability_veto
                    ├─► compliance_veto
                    └─► fidelity_veto
                          └─► tradeoff_veto  (fan-in: all 4 gates present)
                                └─► blast_radius
                                      └─► calibration
                                            └─► state_persistence
                                                  └─► reflect_decide
                                                        └─► required_actions
                                                              └─► isa_yaml_patch
                                                                    └─► sandbox_rec
                                                                          └─► human_review_gate
                                                                                └─► END

The four veto-gate nodes run as a LangGraph parallel fan-out:
  parallel_reviewer → [security_veto, reliability_veto,
                        compliance_veto,  fidelity_veto]
                    → tradeoff_veto   (single merged state is passed in)

Section 9 — LangGraph Workflow Wiring.
"""

from langgraph.graph import END, START, StateGraph

from isa_cad.agent.graph_state import AgentState
from isa_cad.agent.nodes import (
    BlastRadiusNode,
    BuildDesignDeltaNode,
    CalibrationAndBiasAdjustmentNode,
    ContextAndFreshnessNode,
    HumanDecisionProcessorNode,
    HumanReviewGateNode,
    IsaYamlPatchNode,
    RequiredActionsNode,
    ReflectAndDecideNode,
    SandboxRecommendationNode,
    StatePersistenceNode,
    TradeoffAndVetoGateNode,
)
from isa_cad.agent.reviewers import ParallelReviewerNode
from isa_cad.agent.veto import (
    ComplianceVetoGate,
    FidelityVetoGate,
    ReliabilityVetoGate,
    SecurityVetoGate,
)


# ── Node name constants ───────────────────────────────────────────────────────

_CONTEXT_FRESHNESS    = "context_freshness"
_BUILD_DELTA          = "build_design_delta"
_PARALLEL_REVIEWER    = "parallel_reviewer"
_SECURITY_VETO        = "security_veto"
_RELIABILITY_VETO     = "reliability_veto"
_COMPLIANCE_VETO      = "compliance_veto"
_FIDELITY_VETO        = "fidelity_veto"
_TRADEOFF_VETO        = "tradeoff_veto"
_BLAST_RADIUS         = "blast_radius"
_CALIBRATION          = "calibration"
_STATE_PERSISTENCE    = "state_persistence"
_REFLECT_DECIDE       = "reflect_decide"
_REQUIRED_ACTIONS     = "required_actions"
_ISA_YAML_PATCH       = "isa_yaml_patch"
_SANDBOX_REC          = "sandbox_recommendation"
_HUMAN_REVIEW_GATE    = "human_review_gate"
_HUMAN_DECISION       = "human_decision_processor"


def build_graph(
    *,
    context_freshness_node:    ContextAndFreshnessNode    | None = None,
    build_delta_node:          BuildDesignDeltaNode        | None = None,
    parallel_reviewer_node:    ParallelReviewerNode        | None = None,
    security_veto_node:        SecurityVetoGate            | None = None,
    reliability_veto_node:     ReliabilityVetoGate         | None = None,
    compliance_veto_node:      ComplianceVetoGate          | None = None,
    fidelity_veto_node:        FidelityVetoGate            | None = None,
    tradeoff_veto_node:        TradeoffAndVetoGateNode     | None = None,
    blast_radius_node:         BlastRadiusNode             | None = None,
    calibration_node:          CalibrationAndBiasAdjustmentNode | None = None,
    persistence_node:          StatePersistenceNode        | None = None,
    reflect_decide_node:       ReflectAndDecideNode        | None = None,
    required_actions_node:     RequiredActionsNode         | None = None,
    isa_yaml_patch_node:       IsaYamlPatchNode            | None = None,
    sandbox_rec_node:          SandboxRecommendationNode   | None = None,
    human_review_gate_node:    HumanReviewGateNode         | None = None,
    human_decision_node:       HumanDecisionProcessorNode  | None = None,
) -> StateGraph:
    """
    Construct and compile the ISA-CAD LangGraph pipeline.

    All nodes have injectable defaults so unit tests can substitute
    lightweight fakes without touching global singletons.

    Returns the compiled graph (a ``CompiledGraph`` which is also a
    ``Runnable[AgentState, AgentState]``).
    """

    # ── Instantiate defaults ──────────────────────────────────────────────────
    cf_node   = context_freshness_node   or ContextAndFreshnessNode()
    bd_node   = build_delta_node         or BuildDesignDeltaNode()
    pr_node   = parallel_reviewer_node   or ParallelReviewerNode()
    sv_node   = security_veto_node       or SecurityVetoGate()
    rv_node   = reliability_veto_node    or ReliabilityVetoGate()
    cv_node   = compliance_veto_node     or ComplianceVetoGate()
    fv_node   = fidelity_veto_node       or FidelityVetoGate()
    tv_node   = tradeoff_veto_node       or TradeoffAndVetoGateNode()
    br_node   = blast_radius_node        or BlastRadiusNode()
    cal_node  = calibration_node         or CalibrationAndBiasAdjustmentNode()
    sp_node   = persistence_node         or StatePersistenceNode()
    rd_node   = reflect_decide_node      or ReflectAndDecideNode()
    ra_node   = required_actions_node    or RequiredActionsNode()
    iy_node   = isa_yaml_patch_node      or IsaYamlPatchNode()
    sr_node   = sandbox_rec_node         or SandboxRecommendationNode()
    hrg_node  = human_review_gate_node   or HumanReviewGateNode()
    hdp_node  = human_decision_node      or HumanDecisionProcessorNode()

    # ── Build graph ───────────────────────────────────────────────────────────
    g = StateGraph(AgentState)

    # Register nodes
    g.add_node(_CONTEXT_FRESHNESS,  cf_node)
    g.add_node(_BUILD_DELTA,        bd_node)
    g.add_node(_PARALLEL_REVIEWER,  pr_node)
    g.add_node(_SECURITY_VETO,      sv_node)
    g.add_node(_RELIABILITY_VETO,   rv_node)
    g.add_node(_COMPLIANCE_VETO,    cv_node)
    g.add_node(_FIDELITY_VETO,      fv_node)
    g.add_node(_TRADEOFF_VETO,      tv_node)
    g.add_node(_BLAST_RADIUS,       br_node)
    g.add_node(_CALIBRATION,        cal_node)
    g.add_node(_STATE_PERSISTENCE,  sp_node)
    g.add_node(_REFLECT_DECIDE,     rd_node)
    g.add_node(_REQUIRED_ACTIONS,   ra_node)
    g.add_node(_ISA_YAML_PATCH,     iy_node)
    g.add_node(_SANDBOX_REC,        sr_node)
    g.add_node(_HUMAN_REVIEW_GATE,  hrg_node)
    g.add_node(_HUMAN_DECISION,     hdp_node)

    # ── Linear prefix ─────────────────────────────────────────────────────────
    g.add_edge(START,             _CONTEXT_FRESHNESS)
    g.add_edge(_CONTEXT_FRESHNESS, _BUILD_DELTA)
    g.add_edge(_BUILD_DELTA,       _PARALLEL_REVIEWER)

    # ── Parallel veto-gate fan-out ─────────────────────────────────────────────
    # parallel_reviewer → [security_veto, reliability_veto,
    #                       compliance_veto, fidelity_veto]
    for veto in (_SECURITY_VETO, _RELIABILITY_VETO, _COMPLIANCE_VETO, _FIDELITY_VETO):
        g.add_edge(_PARALLEL_REVIEWER, veto)

    # Fan-in: all four gates → tradeoff_veto
    # LangGraph merges concurrent branches automatically before the join node.
    for veto in (_SECURITY_VETO, _RELIABILITY_VETO, _COMPLIANCE_VETO, _FIDELITY_VETO):
        g.add_edge(veto, _TRADEOFF_VETO)

    # ── Linear suffix ─────────────────────────────────────────────────────────
    g.add_edge(_TRADEOFF_VETO,     _BLAST_RADIUS)
    g.add_edge(_BLAST_RADIUS,      _CALIBRATION)
    g.add_edge(_CALIBRATION,       _STATE_PERSISTENCE)
    g.add_edge(_STATE_PERSISTENCE, _REFLECT_DECIDE)
    g.add_edge(_REFLECT_DECIDE,    _REQUIRED_ACTIONS)
    g.add_edge(_REQUIRED_ACTIONS,  _ISA_YAML_PATCH)
    g.add_edge(_ISA_YAML_PATCH,    _SANDBOX_REC)
    g.add_edge(_SANDBOX_REC,       _HUMAN_REVIEW_GATE)
    g.add_edge(_HUMAN_REVIEW_GATE, _HUMAN_DECISION)
    g.add_edge(_HUMAN_DECISION,    END)

    return g.compile()


def build_llm_graph(
    llm=None,  # BaseChatModel | None
    **kwargs,
) -> "StateGraph":
    """
    Convenience factory — identical to ``build_graph()`` but swaps in
    ``LLMParallelReviewerNode`` as the parallel reviewer.

    Parameters
    ----------
    llm
        Optional pre-built ``BaseChatModel``.  When ``None``, the provider
        is chosen from ``settings.LLM_PROVIDER`` (default: anthropic).
    **kwargs
        All other ``build_graph()`` keyword arguments, forwarded as-is.
        Passing ``parallel_reviewer_node`` explicitly overrides the LLM node.
    """
    from isa_cad.agent.reviewers.llm import LLMParallelReviewerNode

    kwargs.setdefault("parallel_reviewer_node", LLMParallelReviewerNode(llm=llm))
    return build_graph(**kwargs)
