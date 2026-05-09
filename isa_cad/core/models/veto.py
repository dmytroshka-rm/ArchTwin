from __future__ import annotations

from pydantic import Field

from .base import ISABaseModel
from .enums import VetoGateResult, VetoGateType


class VetoGate(ISABaseModel):
    """
    Represents a veto gate result.
    G_j in recommendation_score formula:
        PASSED   → 1.0
        DEGRADED → 0.5 (only if policy explicitly allows it)
        BLOCKED  → 0.0
    """
    gate_type: VetoGateType
    result: VetoGateResult = Field(VetoGateResult.PASSED)
    multiplier: float = Field(1.0, ge=0.0, le=1.0, description="G_j value used in score formula")
    reason: str | None = Field(None, description="Human-readable reason for veto or pass")
    required_action: str | None = Field(None, description="Required remediation action")

    def model_post_init(self, __context: object) -> None:
        # Sync multiplier with result
        if self.result == VetoGateResult.PASSED:
            object.__setattr__(self, "multiplier", 1.0)
        elif self.result == VetoGateResult.DEGRADED:
            object.__setattr__(self, "multiplier", 0.5)
        elif self.result == VetoGateResult.BLOCKED:
            object.__setattr__(self, "multiplier", 0.0)

    @property
    def is_blocking(self) -> bool:
        return self.result == VetoGateResult.BLOCKED


class VetoGateSet(ISABaseModel):
    """Aggregated veto gate results for a proposal."""
    security_gate: VetoGate = Field(
        default_factory=lambda: VetoGate(gate_type=VetoGateType.SECURITY)
    )
    reliability_gate: VetoGate = Field(
        default_factory=lambda: VetoGate(gate_type=VetoGateType.RELIABILITY)
    )
    compliance_gate: VetoGate = Field(
        default_factory=lambda: VetoGate(gate_type=VetoGateType.COMPLIANCE)
    )
    fidelity_gate: VetoGate = Field(
        default_factory=lambda: VetoGate(gate_type=VetoGateType.FIDELITY)
    )

    @property
    def all_gates(self) -> list[VetoGate]:
        return [
            self.security_gate,
            self.reliability_gate,
            self.compliance_gate,
            self.fidelity_gate,
        ]

    @property
    def product(self) -> float:
        """PRODUCT_j(G_j) — multiply all gate multipliers together."""
        result = 1.0
        for gate in self.all_gates:
            result *= gate.multiplier
        return result

    @property
    def is_blocked(self) -> bool:
        return any(g.is_blocking for g in self.all_gates)

    @property
    def active_blocks(self) -> list[VetoGate]:
        return [g for g in self.all_gates if g.is_blocking]

    @property
    def active_warnings(self) -> list[VetoGate]:
        return [g for g in self.all_gates if g.result == VetoGateResult.DEGRADED]
