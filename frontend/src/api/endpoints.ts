/**
 * ISA-CAD REST endpoint bindings — all features wired to backend.
 */

import { api } from './client'
import type {
  CanvasOperation,
  OperationValidationResult,
  CanvasComment,
} from '@/generated/canvas-operation.types'
import type {
  SimulationRequest,
  SimulationResult,
  PromotionArtifacts,
} from '@/generated/simulation-result.types'
import type {
  DesignProposal,
  ArchComponent,
  ArchRelation,
  Checkpoint,
} from '@/generated/isa.types'

// ── Capabilities ──────────────────────────────────────────────────────────

export interface BackendCapabilities {
  isa_schema_version: string
  simulation_result_schema_version: string
  canvas_event_schema_version: string
  agent_convention_version: string
  supported_goals: string[]
  supported_reviewers: string[]
}

export const capabilitiesApi = {
  get: () => api.get<BackendCapabilities>('/capabilities'),
}

// ── Canvas operations ─────────────────────────────────────────────────────

export const canvasApi = {
  validateOperation: (op: Omit<CanvasOperation, 'id' | 'status' | 'created_at'>) =>
    api.post<OperationValidationResult>('/canvas/operations', op),

  getComponents: (layerId: string) =>
    api.get<ArchComponent[]>(`/canvas/layers/${layerId}/components`),

  getRelations: (layerId: string) =>
    api.get<ArchRelation[]>(`/canvas/layers/${layerId}/relations`),

  /** Get per-node cost/risk/performance annotations for view modes */
  getAnnotations: (layerId: string) =>
    api.get<NodeAnnotations>(`/canvas/layers/${layerId}/annotations`),
}

// ── Annotation types ──────────────────────────────────────────────────────

export interface CostAnnotation {
  monthly_usd: number
  label: string
  level: 'low' | 'medium' | 'high'
}

export interface SecurityAnnotation {
  risk: 'low' | 'medium' | 'high'
  external_facing: boolean
  has_pii: boolean
  crosses_boundary: boolean
}

export interface PerformanceAnnotation {
  risk: 'low' | 'medium' | 'high'
  p99_ms: number | null
  rps: number | null
}

export interface BlastAnnotation {
  downstream_count: number
  weight: number
  tier: string
}

export interface NodeAnnotation {
  cost: CostAnnotation
  security: SecurityAnnotation
  performance: PerformanceAnnotation
  blast_radius: BlastAnnotation
}

export interface EdgeAnnotation {
  cost: { egress_level: string; label: string | null }
  security: { risk: string }
}

export interface NodeAnnotations {
  nodes: Record<string, NodeAnnotation>
  edges: Record<string, EdgeAnnotation>
}

// ── Layers ────────────────────────────────────────────────────────────────

export const layerApi = {
  list: (baselineRef: string) =>
    api.get<DesignProposal[]>(`/layers?baseline_ref=${encodeURIComponent(baselineRef)}`),

  get: (layerId: string) =>
    api.get<DesignProposal>(`/layers/${layerId}`),

  create: (payload: Pick<DesignProposal, 'title' | 'baseline_ref' | 'optimization_goal'>) =>
    api.post<DesignProposal>('/layers', payload),

  archive: (layerId: string) =>
    api.patch<DesignProposal>(`/layers/${layerId}`, { status: 'archived' }),

  promote: (layerId: string) =>
    api.post<PromotionArtifacts>(`/layers/${layerId}/promote`, {}),
}

// ── Simulations ───────────────────────────────────────────────────────────

export const simulationApi = {
  start: (req: SimulationRequest) =>
    api.post<{ job_id: string }>('/simulations', req),

  getResult: (jobId: string) =>
    api.get<SimulationResult>(`/simulations/${jobId}`),

  cancel: (jobId: string) =>
    api.post<void>(`/simulations/${jobId}/cancel`, {}),

  /** Get prioritized actions from a simulation */
  getActions: (jobId: string) =>
    api.get<PrioritizedActions>(`/simulations/${jobId}/actions`),
}

export interface PrioritizedAction {
  priority: 'blocking' | 'required' | 'recommended' | 'optional'
  role: string
  short_title: string
  detail: string
  full_text: string
}

export interface PrioritizedActions {
  actions: PrioritizedAction[]
}

// ── AI Commands ───────────────────────────────────────────────────────────

export interface AICommandResult {
  action: string
  type: string
  message: string
  result?: Record<string, unknown>
  suggestions?: string[]
}

export const aiApi = {
  command: (command: string, context?: Record<string, unknown>) =>
    api.post<AICommandResult>('/ai/command', { command, context: context ?? {} }),
}

// ── Checkpoints ───────────────────────────────────────────────────────────

export const checkpointApi = {
  list: () => api.get<Checkpoint[]>('/checkpoints'),
  get:  (id: string) => api.get<Checkpoint>(`/checkpoints/${id}`),
  resume: (id: string) => api.post<void>(`/checkpoints/${id}/resume`, {}),
}

// ── Comments ──────────────────────────────────────────────────────────────

export const commentsApi = {
  list: (layerId: string) =>
    api.get<CanvasComment[]>(`/layers/${layerId}/comments`),

  create: (layerId: string, comment: Omit<CanvasComment, 'id' | 'created_at'>) =>
    api.post<CanvasComment>(`/layers/${layerId}/comments`, comment),

  resolve: (layerId: string, commentId: string) =>
    api.patch<CanvasComment>(`/layers/${layerId}/comments/${commentId}`, { resolved: true }),
}

// ── Billing ──────────────────────────────────────────────────────────────────

import type {
  SubscriptionInfo,
  EntitlementCheck,
  CheckoutResponse,
  PortalResponse,
  Plan,
} from '@/generated/billing.types'

export const billingApi = {
  getSubscription: () =>
    api.get<SubscriptionInfo>('/billing/subscription'),

  getPlans: () =>
    api.get<Plan[]>('/billing/plans'),

  createCheckout: (planKey: string) =>
    api.post<CheckoutResponse>('/billing/checkout', { plan_key: planKey }),

  openPortal: () =>
    api.post<PortalResponse>('/billing/portal', {}),

  checkEntitlement: (feature: string) =>
    api.get<EntitlementCheck>(`/entitlements/check?feature=${encodeURIComponent(feature)}`),
}
