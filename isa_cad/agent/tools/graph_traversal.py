from __future__ import annotations

"""
isa_cad/agent/tools/graph_traversal.py
========================================
LangChain tool — BFS traversal of the C4 component graph.

Given a source component ID and optional max-depth, returns the list of
reachable component IDs with their graph distances.  Used by reviewers to
reason about propagation paths, dependency chains, and blast radius scope.
"""

import json
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from isa_cad.state.canvas_state import ComponentGraph


class _GraphTraversalInput(BaseModel):
    source_id: str = Field(..., description="ID of the starting component")
    max_depth: int = Field(3, ge=1, le=10,
                           description="Maximum BFS traversal depth (1–10)")


class GraphTraversalTool(BaseTool):
    """
    BFS traversal of the resolved C4 component graph.

    Returns a JSON-serialised dict mapping each reachable component ID
    to its graph distance from the source.

    The graph must be injected at construction time via ``resolved_graph``.
    """

    name: str = "graph_traversal"
    description: str = (
        "Traverse the component graph using BFS from a source component. "
        "Returns all reachable components and their hop-distance from the source. "
        "Use this to understand propagation paths and dependency scope."
    )
    args_schema: Type[BaseModel] = _GraphTraversalInput

    resolved_graph: ComponentGraph = Field(default_factory=ComponentGraph)

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, source_id: str, max_depth: int = 3) -> str:
        distances = self.resolved_graph.bfs_distances(source_id, max_depth)
        if not distances:
            return json.dumps({
                "source_id": source_id,
                "reachable":  {},
                "note": f"No components reachable from '{source_id}' within depth {max_depth}.",
            })
        return json.dumps({
            "source_id": source_id,
            "max_depth": max_depth,
            "reachable": distances,
            "total_reachable": len(distances),
        })
