/**
 * useFirestoreSync — auto-saves canvas state to Firestore and loads on login.
 * Debounces writes so we don't spam Firestore on every drag.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { useAuth } from './useAuth'
import { useSandboxStore } from '@/store/sandboxStore'
import { useCanvasStore } from '@/store/canvasStore'
import {
  saveFullProject,
  loadFullProject,
  deleteComponent as fsDeleteComponent,
  deleteRelation as fsDeleteRelation,
  deleteNodePosition as fsDeletePosition,
  type FullProjectData,
} from './firestore'
import type { ArchComponent } from '@/generated/isa.types'

// ── localStorage fallback ─────────────────────────────────────────────────────

const LOCAL_STORAGE_KEY = 'archtwin-project-data'

function saveToLocalStorage(data: FullProjectData) {
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(data))
  } catch { /* quota exceeded — ignore */ }
}

function loadFromLocalStorage(): FullProjectData | null {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as FullProjectData
  } catch {
    return null
  }
}

const DEFAULT_PROJECT_ID = 'default'
const SAVE_DEBOUNCE_MS = 2000

export function useFirestoreSync() {
  const { user } = useAuth()
  const {
    setBaselineRef, upsertLayer,
    setLayerComponents, setLayerRelations,
  } = useSandboxStore()
  const { setNodeLayout, setActiveLayer } = useCanvasStore()

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadedRef = useRef(false)
  const [firestoreReady, setFirestoreReady] = useState(false)
  const uid = user?.uid

  // ── Restore project data from a FullProjectData object ───────────────────

  const restoreData = useCallback((data: FullProjectData) => {
    setBaselineRef(data.baseline_ref)

    for (const layer of data.layers) {
      upsertLayer(layer)
      if (data.components[layer.id]) {
        setLayerComponents(layer.id, data.components[layer.id])
      }
      if (data.relations[layer.id]) {
        setLayerRelations(layer.id, data.relations[layer.id])
      }
    }

    for (const [nodeId, pos] of Object.entries(data.positions)) {
      setNodeLayout(nodeId, { x: pos.x, y: pos.y })
    }

    if (data.layers.length > 0) {
      setActiveLayer(data.layers[0].id)
    }
  }, [setBaselineRef, upsertLayer, setLayerComponents, setLayerRelations, setNodeLayout, setActiveLayer])

  // ── Load from Firestore on login (with localStorage fallback) ──────────

  useEffect(() => {
    if (!uid) {
      // No user — try localStorage anyway
      const local = loadFromLocalStorage()
      if (local && local.layers.length > 0) {
        restoreData(local)
      }
      loadedRef.current = true
      setFirestoreReady(true)
      return
    }
    if (loadedRef.current) return

    loadFullProject(uid, DEFAULT_PROJECT_ID).then((data) => {
      if (!data || data.layers.length === 0) {
        // Firestore empty — try localStorage
        const local = loadFromLocalStorage()
        if (local && local.layers.length > 0) {
          restoreData(local)
        }
        loadedRef.current = true
        setFirestoreReady(true)
        return
      }

      restoreData(data)
      // Also save to localStorage as backup
      saveToLocalStorage(data)

      loadedRef.current = true
      setFirestoreReady(true)
    }).catch((err) => {
      console.warn('Firestore load failed:', err)
      // Fallback to localStorage
      const local = loadFromLocalStorage()
      if (local && local.layers.length > 0) {
        restoreData(local)
      }
      loadedRef.current = true
      setFirestoreReady(true)
    })
  }, [uid, restoreData])

  // ── Auto-save (debounced) ───────────────────────────────────────────────

  const triggerSave = useCallback(() => {
    if (!loadedRef.current) return

    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current)
    }

    saveTimerRef.current = setTimeout(() => {
      const currentLayers = useSandboxStore.getState().layers
      const currentBaselineRef = useSandboxStore.getState().baselineRef
      const currentPositions = useCanvasStore.getState().nodeLayouts

      const layerList = Object.values(currentLayers).map((ld) => ld.proposal)
      const components: Record<string, ArchComponent[]> = {}
      const relations: Record<string, import('@/generated/isa.types').ArchRelation[]> = {}

      for (const ld of Object.values(currentLayers)) {
        components[ld.proposal.id] = ld.components
        relations[ld.proposal.id] = ld.relations
      }

      const positions: Record<string, { x: number; y: number }> = {}
      for (const [id, layout] of Object.entries(currentPositions)) {
        positions[id] = { x: layout.x, y: layout.y }
      }

      const data: FullProjectData = {
        name: 'My Architecture',
        baseline_ref: currentBaselineRef || '',
        layers: layerList,
        components,
        relations,
        positions,
      }

      // Always save to localStorage (instant, reliable)
      saveToLocalStorage(data)

      // Also save to Firestore if user is logged in
      if (uid) {
        saveFullProject(uid, DEFAULT_PROJECT_ID, data).catch((err) => {
          console.warn('Firestore save failed:', err)
        })
      }
    }, SAVE_DEBOUNCE_MS)
  }, [uid])

  // Watch store changes and trigger save
  useEffect(() => {
    if (!loadedRef.current) return

    const unsubSandbox = useSandboxStore.subscribe(() => triggerSave())
    const unsubCanvas = useCanvasStore.subscribe(() => triggerSave())

    return () => {
      unsubSandbox()
      unsubCanvas()
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
  }, [triggerSave])

  // ── Individual delete sync ──────────────────────────────────────────────

  const deleteComponentFromFirestore = useCallback((componentId: string) => {
    if (!uid) return
    fsDeleteComponent(uid, DEFAULT_PROJECT_ID, componentId).catch(() => {})
    fsDeletePosition(uid, DEFAULT_PROJECT_ID, componentId).catch(() => {})
  }, [uid])

  const deleteRelationFromFirestore = useCallback((relationId: string) => {
    if (!uid) return
    fsDeleteRelation(uid, DEFAULT_PROJECT_ID, relationId).catch(() => {})
  }, [uid])

  return {
    deleteComponentFromFirestore,
    deleteRelationFromFirestore,
    isLoaded: loadedRef.current,
    firestoreReady,
  }
}
