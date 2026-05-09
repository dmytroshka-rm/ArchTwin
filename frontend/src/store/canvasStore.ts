/**
 * Canvas store — owns visual layout state and pending operations.
 * Architecture semantics (components, relations) live in sandboxStore.
 * This store owns only: viewport, node positions, selection, pending ops.
 */

import { create } from 'zustand'
import type { CanvasOperation, CanvasOperationStatus } from '@/generated/canvas-operation.types'
import type { Viewport, NodeLayout } from '@/generated/isa.types'

interface CanvasState {
  // Viewport
  viewport: Viewport
  setViewport: (v: Viewport) => void

  // Node layout (layout metadata only — not architecture semantics)
  nodeLayouts: Record<string, NodeLayout>
  setNodeLayout: (nodeId: string, layout: NodeLayout) => void

  // Selection
  selectedNodeIds: string[]
  selectedEdgeIds: string[]
  setSelection: (nodeIds: string[], edgeIds?: string[]) => void
  clearSelection: () => void

  // Pending operations (optimistic — awaiting backend validation)
  pendingOps: CanvasOperation[]
  addPendingOp: (op: CanvasOperation) => void
  resolvePendingOp: (opId: string, status: CanvasOperationStatus, message?: string) => void
  rollbackPendingOp: (opId: string) => void

  // UI state
  isPaletteOpen: boolean
  togglePalette: () => void
  activeLayerId: string | null
  setActiveLayer: (id: string | null) => void
}

export const useCanvasStore = create<CanvasState>((set) => ({
  // Viewport
  viewport: { zoom: 1.0, pan_x: 0, pan_y: 0 },
  setViewport: (viewport) => set({ viewport }),

  // Layouts
  nodeLayouts: {},
  setNodeLayout: (nodeId, layout) =>
    set((s) => ({ nodeLayouts: { ...s.nodeLayouts, [nodeId]: layout } })),

  // Selection
  selectedNodeIds: [],
  selectedEdgeIds: [],
  setSelection: (nodeIds, edgeIds = []) =>
    set({ selectedNodeIds: nodeIds, selectedEdgeIds: edgeIds }),
  clearSelection: () => set({ selectedNodeIds: [], selectedEdgeIds: [] }),

  // Pending ops
  pendingOps: [],
  addPendingOp: (op) =>
    set((s) => ({ pendingOps: [...s.pendingOps, op] })),
  resolvePendingOp: (opId, status, message) =>
    set((s) => ({
      pendingOps: s.pendingOps.map((op) =>
        op.id === opId
          ? { ...op, status, validation_message: message }
          : op,
      ),
    })),
  rollbackPendingOp: (opId) =>
    set((s) => ({ pendingOps: s.pendingOps.filter((op) => op.id !== opId) })),

  // UI
  isPaletteOpen: true,
  togglePalette: () => set((s) => ({ isPaletteOpen: !s.isPaletteOpen })),
  activeLayerId: null,
  setActiveLayer: (id) => set({ activeLayerId: id }),
}))
