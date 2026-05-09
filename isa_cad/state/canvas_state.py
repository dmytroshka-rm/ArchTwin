from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field, field_validator

from isa_cad.core.models.base import ISABaseModel
from isa_cad.core.models.enums import OptimizationGoal, ProposalStatus


class ComponentNode(ISABaseModel):
    """A single node in the C4 Semantic Graph on the Canvas."""
    id: str
    label: str
    tier: str = "standard"           # tier_1 | standard | auxiliary
    component_type: str = "service"  # service | database | queue | gateway | external
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComponentEdge(ISABaseModel):
    """A directed edge between two components in the graph."""
    source_id: str
    target_id: str
    label: str = ""
    protocol: str = ""   # e.g. "HTTPS", "gRPC", "AMQP"
    is_async: bool = False


class ComponentGraph(ISABaseModel):
    """
    The C4 Semantic Graph: nodes + edges.
    Used as baseline and as input for BlastRadiusNode traversal.
    """
    nodes: list[ComponentNode] = Field(default_factory=list)
    edges: list[ComponentEdge] = Field(default_factory=list)

    def get_node(self, node_id: str) -> ComponentNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def neighbors(self, node_id: str) -> list[str]:
        """Return IDs of all direct neighbors (outgoing + incoming edges)."""
        return [
            e.target_id for e in self.edges if e.source_id == node_id
        ] + [
            e.source_id for e in self.edges if e.target_id == node_id
        ]

    def bfs_distances(self, start_id: str, max_depth: int = 5) -> dict[str, int]:
        """
        BFS from start_id.
        Returns {node_id: graph_distance} for all reachable nodes (excluding start).
        """
        visited: dict[str, int] = {start_id: 0}
        queue = [start_id]
        while queue:
            current = queue.pop(0)
            depth = visited[current]
            if depth >= max_depth:
                continue
            for neighbor in self.neighbors(current):
                if neighbor not in visited:
                    visited[neighbor] = depth + 1
                    queue.append(neighbor)
        visited.pop(start_id, None)
        return visited


class SandboxLayer(ISABaseModel):
    """
    A proposed design variation on top of the baseline.
    Each layer is a named set of component additions/modifications.
    """
    id: str
    title: str
    status: ProposalStatus = ProposalStatus.SANDBOX_LAYER
    added_nodes: list[ComponentNode] = Field(default_factory=list)
    modified_nodes: list[ComponentNode] = Field(default_factory=list)
    removed_node_ids: list[str] = Field(default_factory=list)
    added_edges: list[ComponentEdge] = Field(default_factory=list)
    removed_edge_keys: list[tuple[str, str]] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def apply_to(self, graph: ComponentGraph) -> ComponentGraph:
        """
        Apply this sandbox layer on top of a ComponentGraph.
        Returns a new graph — does NOT mutate the original.
        """
        nodes = {n.id: n for n in graph.nodes}
        edges = {(e.source_id, e.target_id): e for e in graph.edges}

        # Remove nodes
        for nid in self.removed_node_ids:
            nodes.pop(nid, None)

        # Add / overwrite nodes
        for n in self.added_nodes + self.modified_nodes:
            nodes[n.id] = n

        # Remove edges
        for key in self.removed_edge_keys:
            edges.pop(key, None)

        # Add edges
        for e in self.added_edges:
            edges[(e.source_id, e.target_id)] = e

        return ComponentGraph(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
        )


class CanvasSessionState(ISABaseModel):
    """
    Full persistent state of a Canvas session.
    Stored before async refresh (StatePersistenceNode) and
    restored when the session resumes.
    Section 6.2 + Section 4 (LangGraph Workflow).
    """
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Core design data
    baseline_ref: str
    baseline_graph: ComponentGraph = Field(default_factory=ComponentGraph)
    sandbox_layers: list[SandboxLayer] = Field(default_factory=list)
    active_layer_ids: list[str] = Field(default_factory=list)

    # Goal
    optimization_goal: OptimizationGoal = OptimizationGoal.BALANCED

    # Freshness tracking
    last_observed_graph_refresh: datetime | None = None
    observed_graph_stale: bool = False

    # Partial reviewer outputs (preserved across async waits)
    partial_outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="e.g. {'CostReviewerNode': {...}, 'PerformanceReviewerNode': {...}}",
    )

    # Assumptions collected during session
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("session_id")
    @classmethod
    def session_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id must not be empty")
        return v

    def get_layer(self, layer_id: str) -> SandboxLayer | None:
        for layer in self.sandbox_layers:
            if layer.id == layer_id:
                return layer
        return None

    def add_layer(self, layer: SandboxLayer) -> None:
        existing_ids = {l.id for l in self.sandbox_layers}
        if layer.id in existing_ids:
            raise ValueError(f"Sandbox layer '{layer.id}' already exists in session")
        self.sandbox_layers.append(layer)
        self.updated_at = datetime.now(UTC)

    def activate_layer(self, layer_id: str) -> None:
        if layer_id not in {l.id for l in self.sandbox_layers}:
            raise ValueError(f"Layer '{layer_id}' not found in session")
        if layer_id not in self.active_layer_ids:
            self.active_layer_ids.append(layer_id)
            self.updated_at = datetime.now(UTC)

    def deactivate_layer(self, layer_id: str) -> None:
        self.active_layer_ids = [lid for lid in self.active_layer_ids if lid != layer_id]
        self.updated_at = datetime.now(UTC)

    def resolved_graph(self) -> ComponentGraph:
        """
        Apply all active sandbox layers on top of the baseline graph in order.
        Returns the merged ComponentGraph representing the current proposal state.
        """
        graph = self.baseline_graph
        for layer_id in self.active_layer_ids:
            layer = self.get_layer(layer_id)
            if layer:
                graph = layer.apply_to(graph)
        return graph

    def mark_refreshed(self) -> None:
        self.last_observed_graph_refresh = datetime.now(UTC)
        self.observed_graph_stale = False
        self.updated_at = datetime.now(UTC)

    def mark_stale(self) -> None:
        self.observed_graph_stale = True
        self.updated_at = datetime.now(UTC)
