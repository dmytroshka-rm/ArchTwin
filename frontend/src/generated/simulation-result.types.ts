/**
 * @generated — DO NOT EDIT MANUALLY
 * Source of truth: backend/contracts/simulation-result.schema.json
 * Synchronized with ISA-CAD Backend Convention v0.5.3 / Frontend v0.6
 */

import type {
  OptimizationGoal,
  VetoGateResult,
  FidelityMode,
  BlastRadiusEntry,
} from './isa.types'

// ── Simulation request (Section 6.2) ──────────────────────────────────────

export interface FreshnessPolicy {
  warn_after_hours: number
  exploratory_after_days: number
  block_final_decision_below_confidence: number
}

export interface SimulationRequest {
  baseline_ref: string
  proposal_refs: string[]
  optimization_goal: OptimizationGoal
  reviewers: Array<'cost' | 'performance' | 'security'>
  include_blast_radius: boolean
  include_calibration: boolean
  freshness_policy?: FreshnessPolicy
}

// ── Veto gates ────────────────────────────────────────────────────────────

export interface VetoGates {
  security: VetoGateResult
  reliability: VetoGateResult
  compliance: VetoGateResult
  fidelity?: VetoGateResult
  tradeoff?: VetoGateResult
}

// ── Fidelity report ───────────────────────────────────────────────────────

export interface FidelityReport {
  base_confidence: number
  freshness_score: number
  staleness_penalty: number
  adjusted_confidence: number
  mode: FidelityMode
  calibration_note?: string
  safety_buffer_applied?: boolean
  data_ages?: {
    inventory_hours?: number
    metrics_hours?: number
    pricing_hours?: number
  }
}

// ── Reviewer output ───────────────────────────────────────────────────────

export type ReviewerStatus = 'pass' | 'fail' | 'warn' | 'degraded' | 'skipped'

export interface ReviewerOutput {
  reviewer: 'cost' | 'performance' | 'security'
  status: ReviewerStatus
  score: number
  summary: string
  findings: string[]
  blocked: boolean
  block_reasons?: string[]
}

// ── Recommendation ────────────────────────────────────────────────────────

export interface Recommendation {
  winner: string
  recommendation_score: number
  blocked: boolean
  optimization_goal: OptimizationGoal
  rationale?: string
  vetoed_by?: string[]
}

// ── Trade-off matrix (Section 8.2) ────────────────────────────────────────

export interface TradeoffMatrixRow {
  proposal_id: string
  label: string
  is_baseline: boolean
  cost_score: number
  performance_score: number
  security_score: number
  reliability_score: number
  complexity_score: number
  fidelity_score: number
  veto_status: 'pass' | 'fail' | 'warn'
  recommendation_score: number
  optimization_goal: OptimizationGoal
  blocked: boolean
}

// ── Blast radius summary ──────────────────────────────────────────────────

export interface BlastRadiusSummary {
  high_risk_count: number
  total_impacted: number
  tier_1_count: number
  components: BlastRadiusEntry[]
}

// ── Required actions ──────────────────────────────────────────────────────

export interface RequiredActions {
  developer: string[]
  architect: string[]
  security_ops: string[]
}

// ── Simulation result (Section 6.3) ───────────────────────────────────────

export type SimulationStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface SimulationResult {
  job_id: string
  status: SimulationStatus
  recommendation: Recommendation | null
  veto_gates: VetoGates
  fidelity: FidelityReport
  trade_off_matrix: TradeoffMatrixRow[]
  blast_radius: BlastRadiusSummary | null
  reviewer_outputs: ReviewerOutput[]
  required_actions: RequiredActions
  error?: string
}

// ── Real-time event stream (Section 6.4) ──────────────────────────────────

export type SimulationEventType =
  | 'simulation.started'
  | 'simulation.reviewer.completed'
  | 'simulation.veto.triggered'
  | 'simulation.completed'
  | 'simulation.failed'
  | 'observed_graph.refresh.required'
  | 'checkpoint.saved'

export interface SimulationEvent {
  event: SimulationEventType
  payload: {
    job_id: string
    reviewer?: string
    status?: string
    partial_result_ref?: string
    gate?: string
    reason?: string
    graph_ref?: string
    resume_checkpoint?: string
  }
}

// ── Promotion wizard ──────────────────────────────────────────────────────

export interface PromotionArtifacts {
  isa_yaml_patch: string
  adr_draft: string
  required_actions: RequiredActions
  pr_description: string
  confidence_check: {
    adjusted_confidence: number
    allowed: boolean
    block_reason?: string
  }
}
