from __future__ import annotations

"""
isa_cad/agent/tools/component_lookup.py
=========================================
LangChain tool — look up a single component by ID in the resolved graph.

Returns the component's label, tier, component_type, and metadata.
Used by reviewers to check properties of specific nodes (e.g., is this
component Tier-1? is it a database? does it have PII metadata?).
"""

import json
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from isa_cad.state.canvas_state import ComponentGraph


class _ComponentLookupInput(BaseModel):
    component_id: str = Field(..., description="ID of the component to look up")


class ComponentLookupTool(BaseTool):
    """
    Look up a component by ID in the resolved C4 component graph.

    Returns the component's label, tier, component_type, and any
    custom metadata attached to it.
    """

    name: str = "component_lookup"
    description: str = (
        "Look up a specific component by ID in the architecture graph. "
        "Returns the component's label, tier (tier_1 | standard | auxiliary), "
        "component_type (service | database | queue | gateway | external), "
        "and any metadata. Use this to check properties of a specific node."
    )
    args_schema: Type[BaseModel] = _ComponentLookupInput

    resolved_graph: ComponentGraph = Field(default_factory=ComponentGraph)

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, component_id: str) -> str:
        node = self.resolved_graph.get_node(component_id)
        if node is None:
            return json.dumps({
                "found": False,
                "component_id": component_id,
                "error": f"Component '{component_id}' not found in the resolved graph.",
            })
        return json.dumps({
            "found":          True,
            "id":             node.id,
            "label":          node.label,
            "tier":           node.tier,
            "component_type": node.component_type,
            "metadata":       node.metadata,
        })
