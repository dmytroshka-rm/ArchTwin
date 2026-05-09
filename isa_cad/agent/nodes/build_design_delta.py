from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isa_cad.agent.graph_state import AgentState
from isa_cad.state.canvas_state import (
    CanvasSessionState,
    ComponentEdge,
    ComponentGraph,
    ComponentNode,
    SandboxLayer,
)


# ── Delta model ───────────────────────────────────────────────────────────────

@dataclass
class DesignDelta:
    """
    Structured diff between baseline graph and the resolved proposal graph.
    Produced by BuildDesignDeltaNode; consumed by reviewer nodes and
    BlastRadiusNode to understand what changed.
    """
    baseline_node_count: int = 0
    proposed_node_count: int = 0
    baseline_edge_count: int = 0
    proposed_edge_count: int = 0

    added_nodes:    list[ComponentNode] = field(default_factory=list)
    removed_nodes:  list[ComponentNode] = field(default_factory=list)
    modified_nodes: list[ComponentNode] = field(default_factory=list)

    added_edges:   list[ComponentEdge] = field(default_factory=list)
    removed_edges: list[ComponentEdge] = field(default_factory=list)

    # Primary source: the component most directly changed (used by BlastRadiusNode)
    primary_source_id: str = ""

    # Layer IDs that contributed to this delta
    contributing_layer_ids: list[str] = field(default_factory=list)

    # Human-readable summary
    summary: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_nodes
            or self.removed_nodes
            or self.modified_nodes
            or self.added_edges
            or self.removed_edges
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_node_count":  self.baseline_node_count,
            "proposed_node_count":  self.proposed_node_count,
            "baseline_edge_count":  self.baseline_edge_count,
            "proposed_edge_count":  self.proposed_edge_count,
            "added_nodes":          [n.model_dump() for n in self.added_nodes],
            "removed_nodes":        [n.model_dump() for n in self.removed_nodes],
            "modified_nodes":       [n.model_dump() for n in self.modified_nodes],
            "added_edges":          [e.model_dump() for e in self.added_edges],
            "removed_edges":        [e.model_dump() for e in self.removed_edges],
            "primary_source_id":    self.primary_source_id,
            "contributing_layers":  self.contributing_layer_ids,
            "has_changes":          self.has_changes,
            "summary":              self.summary,
        }


# ── Node ─────────────────────────────────────────────────────────────────────

class BuildDesignDeltaNode:
    """
    LangGraph node — second in the workflow (after ContextAndFreshnessNode).

    Computes the structural diff between:
        baseline_graph  (canvas_session.baseline_graph)
        resolved_graph  (baseline + all active sandbox layers applied)

    Outputs written to AgentState:
        design_delta        (dict representation of DesignDelta)
        source_component_id (primary modified component for blast radius)
    """

    def __call__(self, state: AgentState) -> AgentState:
        session: CanvasSessionState = state.get("canvas_session")  # type: ignore[assignment]
        resolved: ComponentGraph    = state.get("resolved_graph")  # type: ignore[assignment]

        if session is None or resolved is None:
            return {
                **state,
                "design_delta": DesignDelta(summary="No session/graph available.").to_dict(),
                "source_component_id": "",
            }

        delta = self._compute_delta(
            baseline=session.baseline_graph,
            proposed=resolved,
            active_layer_ids=session.active_layer_ids,
            layers=session.sandbox_layers,
        )

        return {
            **state,
            "design_delta":        delta.to_dict(),
            "source_component_id": delta.primary_source_id,
        }

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_delta(
        baseline: ComponentGraph,
        proposed: ComponentGraph,
        active_layer_ids: list[str],
        layers: list[SandboxLayer],
    ) -> DesignDelta:
        baseline_nodes = {n.id: n for n in baseline.nodes}
        proposed_nodes = {n.id: n for n in proposed.nodes}
        baseline_edges = {(e.source_id, e.target_id): e for e in baseline.edges}
        proposed_edges = {(e.source_id, e.target_id): e for e in proposed.edges}

        # Node diff
        added_ids   = set(proposed_nodes) - set(baseline_nodes)
        removed_ids = set(baseline_nodes) - set(proposed_nodes)
        common_ids  = set(baseline_nodes) & set(proposed_nodes)

        added_nodes   = [proposed_nodes[i] for i in sorted(added_ids)]
        removed_nodes = [baseline_nodes[i] for i in sorted(removed_ids)]
        modified_nodes = [
            proposed_nodes[i]
            for i in sorted(common_ids)
            if proposed_nodes[i] != baseline_nodes[i]
        ]

        # Edge diff
        added_edge_keys   = set(proposed_edges) - set(baseline_edges)
        removed_edge_keys = set(baseline_edges) - set(proposed_edges)
        added_edges   = [proposed_edges[k] for k in sorted(added_edge_keys)]
        removed_edges = [baseline_edges[k] for k in sorted(removed_edge_keys)]

        # Primary source: prefer first added node, then first modified node
        primary_source_id = ""
        if added_nodes:
            primary_source_id = added_nodes[0].id
        elif modified_nodes:
            primary_source_id = modified_nodes[0].id
        elif removed_nodes:
            # When a node is removed, the blast radius source is one of its
            # former neighbours in the baseline graph
            former_neighbours = [
                e.target_id if e.source_id == removed_nodes[0].id else e.source_id
                for e in baseline.edges
                if removed_nodes[0].id in (e.source_id, e.target_id)
            ]
            primary_source_id = former_neighbours[0] if former_neighbours else ""

        contributing = [lid for lid in active_layer_ids]

        summary = _build_summary(
            added_nodes, removed_nodes, modified_nodes,
            added_edges, removed_edges,
        )

        return DesignDelta(
            baseline_node_count=len(baseline_nodes),
            proposed_node_count=len(proposed_nodes),
            baseline_edge_count=len(baseline_edges),
            proposed_edge_count=len(proposed_edges),
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            modified_nodes=modified_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
            primary_source_id=primary_source_id,
            contributing_layer_ids=contributing,
            summary=summary,
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_summary(
    added_nodes:    list[ComponentNode],
    removed_nodes:  list[ComponentNode],
    modified_nodes: list[ComponentNode],
    added_edges:    list[ComponentEdge],
    removed_edges:  list[ComponentEdge],
) -> str:
    parts: list[str] = []
    if added_nodes:
        parts.append(f"+{len(added_nodes)} node(s): {[n.id for n in added_nodes]}")
    if removed_nodes:
        parts.append(f"-{len(removed_nodes)} node(s): {[n.id for n in removed_nodes]}")
    if modified_nodes:
        parts.append(f"~{len(modified_nodes)} modified: {[n.id for n in modified_nodes]}")
    if added_edges:
        parts.append(f"+{len(added_edges)} edge(s)")
    if removed_edges:
        parts.append(f"-{len(removed_edges)} edge(s)")
    if not parts:
        return "No structural changes detected."
    return "Delta: " + ", ".join(parts) + "."
