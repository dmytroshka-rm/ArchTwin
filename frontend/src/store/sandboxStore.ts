/**
 * Sandbox store — owns canonical architecture semantic state per layer.
 * Components and relations here are BACKEND-VALIDATED objects.
 * Optimistic draft objects are in canvasStore.pendingOps until confirmed.
 */

import { create } from 'zustand'
import type { ArchComponent, ArchRelation, DesignProposal } from '@/generated/isa.types'

interface LayerData {
  proposal: DesignProposal
  components: ArchComponent[]
  relations: ArchRelation[]
  isLoading: boolean
  lastFetchedAt: string | null
}

interface SandboxState {
  // All known layers (key = layer id)
  layers: Record<string, LayerData>

  // Currently compared layers (for trade-off matrix)
  comparedLayerIds: string[]

  // Baseline ref
  baselineRef: string | null
  setBaselineRef: (ref: string) => void

  // Layer CRUD
  upsertLayer: (proposal: DesignProposal) => void
  removeLayer: (layerId: string) => void
  setLayerLoading: (layerId: string, loading: boolean) => void
  setLayerComponents: (layerId: string, components: ArchComponent[]) => void
  setLayerRelations:  (layerId: string, relations: ArchRelation[]) => void

  // Comparison selection
  setComparedLayers: (ids: string[]) => void

  // Single component/relation mutations (from validated backend responses)
  upsertComponent: (layerId: string, component: ArchComponent) => void
  removeComponent: (layerId: string, componentId: string) => void
  upsertRelation:  (layerId: string, relation: ArchRelation)  => void
  removeRelation:  (layerId: string, relationId: string)      => void

  // Selectors
  getLayer:     (id: string) => LayerData | undefined
  getComponent: (layerId: string, componentId: string) => ArchComponent | undefined
}

export const useSandboxStore = create<SandboxState>((set, get) => ({
  layers: {},
  comparedLayerIds: [],
  baselineRef: null,

  setBaselineRef: (ref) => set({ baselineRef: ref }),

  upsertLayer: (proposal) =>
    set((s) => ({
      layers: {
        ...s.layers,
        [proposal.id]: {
          proposal,
          components: s.layers[proposal.id]?.components ?? [],
          relations:  s.layers[proposal.id]?.relations  ?? [],
          isLoading:  false,
          lastFetchedAt: s.layers[proposal.id]?.lastFetchedAt ?? null,
        },
      },
    })),

  removeLayer: (layerId) =>
    set((s) => {
      const { [layerId]: _, ...rest } = s.layers
      return { layers: rest }
    }),

  setLayerLoading: (layerId, loading) =>
    set((s) => ({
      layers: {
        ...s.layers,
        [layerId]: { ...s.layers[layerId], isLoading: loading },
      },
    })),

  setLayerComponents: (layerId, components) =>
    set((s) => ({
      layers: {
        ...s.layers,
        [layerId]: {
          ...s.layers[layerId],
          components,
          lastFetchedAt: new Date().toISOString(),
        },
      },
    })),

  setLayerRelations: (layerId, relations) =>
    set((s) => ({
      layers: {
        ...s.layers,
        [layerId]: { ...s.layers[layerId], relations },
      },
    })),

  setComparedLayers: (ids) => set({ comparedLayerIds: ids }),

  upsertComponent: (layerId, component) =>
    set((s) => {
      const layer = s.layers[layerId]
      if (!layer) return {}
      const existing = layer.components.filter((c) => c.id !== component.id)
      return {
        layers: {
          ...s.layers,
          [layerId]: { ...layer, components: [...existing, component] },
        },
      }
    }),

  removeComponent: (layerId, componentId) =>
    set((s) => {
      const layer = s.layers[layerId]
      if (!layer) return {}
      return {
        layers: {
          ...s.layers,
          [layerId]: {
            ...layer,
            components: layer.components.filter((c) => c.id !== componentId),
          },
        },
      }
    }),

  upsertRelation: (layerId, relation) =>
    set((s) => {
      const layer = s.layers[layerId]
      if (!layer) return {}
      const existing = layer.relations.filter((r) => r.id !== relation.id)
      return {
        layers: {
          ...s.layers,
          [layerId]: { ...layer, relations: [...existing, relation] },
        },
      }
    }),

  removeRelation: (layerId, relationId) =>
    set((s) => {
      const layer = s.layers[layerId]
      if (!layer) return {}
      return {
        layers: {
          ...s.layers,
          [layerId]: {
            ...layer,
            relations: layer.relations.filter((r) => r.id !== relationId),
          },
        },
      }
    }),

  getLayer: (id) => get().layers[id],
  getComponent: (layerId, componentId) =>
    get().layers[layerId]?.components.find((c) => c.id === componentId),
}))
