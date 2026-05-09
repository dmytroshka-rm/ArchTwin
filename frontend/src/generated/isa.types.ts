/**
 * @generated — DO NOT EDIT MANUALLY
 * Source of truth: backend/contracts/isa.schema.json
 * Synchronized with ISA-CAD Backend Convention v0.5.3
 */

// ── Enums ──────────────────────────────────────────────────────────────────

export type OptimizationGoal =
  | 'balanced'
  | 'cost_efficiency'
  | 'max_reliability'
  | 'minimal_complexity'

export type ComponentType =
  | 'system'
  | 'container'
  | 'component'
  | 'data_store'
  | 'queue'
  | 'gateway'
  | 'external_system'
  | 'cache'
  | 'service'
  | 'storage'

export type RelationType =
  | 'synchronous'
  | 'asynchronous'
  | 'data_access'
  | 'streaming'
  | 'batch'
  | 'external'

export type DataClassification = 'public' | 'internal' | 'confidential' | 'restricted'

export type TierLevel = 'tier_1' | 'standard' | 'auxiliary'

export type ProposalStatus =
  | 'draft'
  | 'sandbox_layer'
  | 'review_requested'
  | 'changes_requested'
  | 'approved_for_pr'
  | 'promoted'
  | 'archived'
  | 'blocked'
  | 'candidate_for_review'
  | 'approved'

export type VetoGateResult = 'pass' | 'fail' | 'warn' | 'skipped'

export type FidelityMode = 'decision_grade' | 'exploratory_estimate' | 'blocked'

// ── Component ─────────────────────────────────────────────────────────────

export interface ComponentDeployment {
  provider?: string
  region?: string
  scaling?: {
    min_acu?: number
    max_acu?: number
    min_instances?: number
    max_instances?: number
  }
}

export interface ComponentObservedMetrics {
  p99_latency_ms?: number
  requests_per_second?: number
  error_rate?: number
  cache_hit_ratio?: number
  last_updated?: string
}

export interface ArchComponent {
  id: string
  name: string
  type: ComponentType
  technology?: string
  tier?: TierLevel
  data_classification?: DataClassification
  deployment?: ComponentDeployment
  observed_metrics?: ComponentObservedMetrics
  tags?: string[]
  description?: string
}

// ── Relation ──────────────────────────────────────────────────────────────

export interface ArchRelation {
  id: string
  source_id: string
  target_id: string
  type: RelationType
  protocol?: string
  data_classification?: DataClassification
  criticality?: 'high' | 'medium' | 'low'
  crosses_trust_boundary?: boolean
  crosses_bounded_context?: boolean
  adr_required?: boolean
  description?: string
}

// ── Canvas layout ─────────────────────────────────────────────────────────

export interface NodeLayout {
  x: number
  y: number
  width?: number
  height?: number
  collapsed?: boolean
}

export interface Viewport {
  zoom: number
  pan_x: number
  pan_y: number
}

export interface CanvasLayout {
  version: string
  graph_ref: string
  nodes: Record<string, NodeLayout>
  viewport: Viewport
}

// ── Design proposal / sandbox layer ───────────────────────────────────────

export interface DesignDiffOperation {
  op: 'add_component' | 'remove_component' | 'replace_component' | 'add_relation' | 'remove_relation' | 'replace_relation'
  target: string
  value?: Partial<ArchComponent> | Partial<ArchRelation>
}

export interface SimulationFidelity {
  base_confidence: number
  data_freshness_score: number
  confidence_penalty: number
  adjusted_confidence: number
  mode?: FidelityMode
}

export interface BlastRadiusEntry {
  id: string
  name?: string
  tier: TierLevel
  distance: number
  impact_score: number
  risk?: string
  mitigation_hints?: Record<string, string[]>
}

export interface DesignProposal {
  id: string
  title: string
  status: ProposalStatus
  baseline_ref: string
  optimization_goal: OptimizationGoal
  created_by?: string
  created_at?: string
  diff: { operations: DesignDiffOperation[] }
  simulation_fidelity?: SimulationFidelity
  blast_radius?: {
    impacted_stable_components: BlastRadiusEntry[]
    high_risk_count?: number
  }
  adr_required?: boolean
}

// ── Checkpoint ────────────────────────────────────────────────────────────

export interface Checkpoint {
  id: string
  saved_at: string
  canvas_session_id?: string
  baseline_ref: string
  sandbox_layer_ids: string[]
  optimization_goal: OptimizationGoal
  pending_action: string
  resume_node: string
  assumptions: string[]
  resumed: boolean
  resumed_at?: string
}
