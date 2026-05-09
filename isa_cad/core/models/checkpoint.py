from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field, field_validator

from .base import ISABaseModel
from .enums import OptimizationGoal


class PartialReviewerOutput(ISABaseModel):
    """
    Partial output from a reviewer node, preserved in a checkpoint
    so the analysis can resume without re-running completed reviewers.
    """
    node_name: str          # e.g. "CostReviewerNode"
    is_complete: bool       # False = still partial
    payload: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Checkpoint(ISABaseModel):
    """
    Full checkpoint of a Canvas session captured before async Observed Graph
    refresh or any other async wait. Allows seamless resume.
    Section 6.2 of the convention.

    checkpoint:
      id: "checkpoint.canvas-session-2026-05-08-001"
      saved_at: "2026-05-08T10:00:00Z"
      baseline_ref: "architecture.baseline.prod"
      sandbox_layers: [...]
      optimization_goal: "cost_efficiency"
      pending_action: "refresh_observed_graph"
      resume_node: "ContextAndFreshnessNode"
      preserved_outputs: [...]
    """
    id: str = Field(..., description="e.g. 'checkpoint.canvas-session-2026-05-08-001'")
    saved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Canvas identity
    canvas_session_id: str | None = None
    baseline_ref: str = Field(..., description="e.g. 'architecture.baseline.prod'")

    # Active sandbox layers at the time of checkpoint
    sandbox_layer_ids: list[str] = Field(
        default_factory=list,
        description="IDs of active sandbox layers at checkpoint time",
    )

    # Goal
    optimization_goal: OptimizationGoal = Field(OptimizationGoal.BALANCED)

    # Why the checkpoint was created
    pending_action: str = Field(
        "",
        description="e.g. 'refresh_observed_graph', 'await_pricing_update'",
    )

    # Which node to resume from when the async action completes
    resume_node: str = Field(
        "ContextAndFreshnessNode",
        description="LangGraph node name to resume execution at",
    )

    # Partial reviewer outputs preserved across the async gap
    preserved_outputs: list[PartialReviewerOutput] = Field(default_factory=list)

    # Assumptions active at checkpoint time
    assumptions: list[str] = Field(default_factory=list)

    # Whether this checkpoint has been consumed (resumed)
    resumed: bool = False
    resumed_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Checkpoint id must not be empty")
        return v

    def get_output(self, node_name: str) -> PartialReviewerOutput | None:
        for o in self.preserved_outputs:
            if o.node_name == node_name:
                return o
        return None

    def mark_resumed(self) -> None:
        self.resumed = True
        self.resumed_at = datetime.now(UTC)

    @property
    def complete_node_names(self) -> list[str]:
        return [o.node_name for o in self.preserved_outputs if o.is_complete]

    @property
    def partial_node_names(self) -> list[str]:
        return [o.node_name for o in self.preserved_outputs if not o.is_complete]
