from __future__ import annotations

from enum import Enum


class ReviewerType(str, Enum):
    COST = "cost"
    PERFORMANCE = "performance"
    SECURITY = "security"


class ReviewerStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


class VetoGateType(str, Enum):
    SECURITY = "security"
    RELIABILITY = "reliability"
    COMPLIANCE = "compliance"
    FIDELITY = "fidelity"


class VetoGateResult(str, Enum):
    PASSED = "passed"          # G_j = 1.0
    DEGRADED = "degraded"      # G_j = 0.5 — only if policy allows
    BLOCKED = "blocked"        # G_j = 0.0


class OutputMode(str, Enum):
    FINAL_FORECAST = "final_forecast"
    EXPLORATORY_ESTIMATE = "exploratory_estimate"


class ProposalStatus(str, Enum):
    SANDBOX_LAYER = "sandbox_layer"
    CANDIDATE_FOR_REVIEW = "candidate_for_review"
    BLOCKED = "blocked"
    APPROVED = "approved"
    REJECTED = "rejected"


class OptimizationGoal(str, Enum):
    COST_EFFICIENCY = "cost_efficiency"
    MAX_RELIABILITY = "max_reliability"
    MINIMAL_COMPLEXITY = "minimal_complexity"
    BALANCED = "balanced"


class ComparisonMode(str, Enum):
    BASELINE_TO_LAYER = "baseline_to_layer"
    LAYER_TO_LAYER = "layer_to_layer"
    OVERLAY_ANALYSIS = "overlay_analysis"


class ComponentTier(str, Enum):
    TIER_1 = "tier_1"       # Shared DB, Identity Provider, Core API — C_m = 2.0
    STANDARD = "standard"   # Domain API, worker, internal service — C_m = 1.0
    AUXILIARY = "auxiliary" # Logging, metrics, monitoring — C_m = 0.5


class HumanDecision(str, Enum):
    APPROVE_SANDBOX_LAYER = "approve_sandbox_layer"
    REQUEST_REFRESH = "request_refresh"
    ACCEPT_RISK_WITH_ADR = "accept_risk_with_adr"
    BLOCK_PROPOSAL = "block_proposal"
    MODIFY_GOAL = "modify_goal"


class CacheContext(str, Enum):
    CDN = "cdn"                   # CHR = 0.85
    INTERNAL_CACHE = "internal"   # CHR = 0.70
    UNKNOWN = "unknown"           # CHR = 0.00
