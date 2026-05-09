/**
 * @generated — DO NOT EDIT MANUALLY
 * Source of truth: backend/contracts/canvas-operation.schema.json
 * Synchronized with ISA-CAD Frontend Canvas Convention v0.6
 */

import type { ArchComponent, ArchRelation } from './isa.types'

// ── Operation types ───────────────────────────────────────────────────────

export type CanvasOperationType =
  | 'add_component'
  | 'remove_component'
  | 'update_component'
  | 'add_relation'
  | 'remove_relation'
  | 'update_relation'
  | 'move_node'
  | 'create_layer'
  | 'archive_layer'
  | 'merge_layer'
  | 'promote_layer'

export type CanvasOperationStatus =
  | 'pending_validation'   // optimistic — awaiting backend
  | 'valid'
  | 'invalid'
  | 'blocked'
  | 'requires_adr'

// ── Operation payload ─────────────────────────────────────────────────────

export interface AddComponentPayload {
  component: Omit<ArchComponent, 'id'> & { id?: string }
  layer_id: string
  position?: { x: number; y: number }
}

export interface UpdateComponentPayload {
  component_id: string
  layer_id: string
  patch: Partial<ArchComponent>
}

export interface RemoveComponentPayload {
  component_id: string
  layer_id: string
}

export interface AddRelationPayload {
  relation: Omit<ArchRelation, 'id'> & { id?: string }
  layer_id: string
}

export interface UpdateRelationPayload {
  relation_id: string
  layer_id: string
  patch: Partial<ArchRelation>
}

export interface RemoveRelationPayload {
  relation_id: string
  layer_id: string
}

export interface MoveNodePayload {
  node_id: string
  layer_id: string
  x: number
  y: number
}

export type CanvasOperationPayload =
  | AddComponentPayload
  | UpdateComponentPayload
  | RemoveComponentPayload
  | AddRelationPayload
  | UpdateRelationPayload
  | RemoveRelationPayload
  | MoveNodePayload

// ── Canvas operation ──────────────────────────────────────────────────────

export interface CanvasOperation {
  id: string
  type: CanvasOperationType
  payload: CanvasOperationPayload
  status: CanvasOperationStatus
  created_at: string
  validation_message?: string
  normalized_result?: Partial<ArchComponent> | Partial<ArchRelation>
}

// ── Backend validation response ───────────────────────────────────────────

export interface OperationValidationResult {
  operation_id: string
  status: CanvasOperationStatus
  normalized: Partial<ArchComponent> | Partial<ArchRelation> | null
  warnings: string[]
  missing_metadata: string[]
  adr_required: boolean
  adr_reason?: string
}

// ── Comment anchor (Section 10.1) ─────────────────────────────────────────

export type CommentTargetType = 'component' | 'relation' | 'layer'

export interface CommentAnchor {
  target_type: CommentTargetType
  target_id: string
  layer_id: string
  field_path?: string
}

export interface CanvasComment {
  id: string
  anchor: CommentAnchor
  author: string
  body: string
  created_at: string
  resolved: boolean
}
