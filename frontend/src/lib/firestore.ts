/**
 * Firestore persistence layer for ISA-CAD.
 *
 * Data structure in Firestore:
 *   users/{uid}/projects/{projectId}
 *     - name, baseline_ref, created_at, updated_at
 *   users/{uid}/projects/{projectId}/layers/{layerId}
 *     - title, status, optimization_goal, baseline_ref
 *   users/{uid}/projects/{projectId}/components/{componentId}
 *     - ...all component fields + layer_id
 *   users/{uid}/projects/{projectId}/relations/{relationId}
 *     - ...all relation fields + layer_id
 *   users/{uid}/projects/{projectId}/positions/{nodeId}
 *     - x, y
 *   users/{uid}/projects/{projectId}/simulations/{jobId}
 *     - ...full simulation result
 */

import {
  collection,
  doc,
  setDoc,
  getDoc,
  getDocs,
  deleteDoc,
  writeBatch,
  serverTimestamp,
  query,
  orderBy,
  limit,
} from 'firebase/firestore'
import { db } from './firebase'
import type { ArchComponent, ArchRelation, DesignProposal } from '@/generated/isa.types'
import type { SimulationResult } from '@/generated/simulation-result.types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function userProjectRef(uid: string, projectId: string) {
  return doc(db, 'users', uid, 'projects', projectId)
}

function layersCol(uid: string, projectId: string) {
  return collection(db, 'users', uid, 'projects', projectId, 'layers')
}

function componentsCol(uid: string, projectId: string) {
  return collection(db, 'users', uid, 'projects', projectId, 'components')
}

function relationsCol(uid: string, projectId: string) {
  return collection(db, 'users', uid, 'projects', projectId, 'relations')
}

function positionsCol(uid: string, projectId: string) {
  return collection(db, 'users', uid, 'projects', projectId, 'positions')
}

function simulationsCol(uid: string, projectId: string) {
  return collection(db, 'users', uid, 'projects', projectId, 'simulations')
}

// ── Project CRUD ──────────────────────────────────────────────────────────────

export interface FirestoreProject {
  id: string
  name: string
  baseline_ref: string
  created_at: unknown
  updated_at: unknown
}

export async function saveProject(uid: string, projectId: string, name: string, baselineRef: string) {
  await setDoc(userProjectRef(uid, projectId), {
    name,
    baseline_ref: baselineRef,
    updated_at: serverTimestamp(),
    created_at: serverTimestamp(),
  }, { merge: true })
}

export async function getProjects(uid: string): Promise<FirestoreProject[]> {
  const snap = await getDocs(collection(db, 'users', uid, 'projects'))
  return snap.docs.map((d) => ({ id: d.id, ...d.data() } as FirestoreProject))
}

export async function deleteProject(uid: string, projectId: string) {
  // Note: in production you'd also delete subcollections
  await deleteDoc(userProjectRef(uid, projectId))
}

// ── Layers ────────────────────────────────────────────────────────────────────

export async function saveLayer(uid: string, projectId: string, layer: DesignProposal) {
  await setDoc(doc(layersCol(uid, projectId), layer.id), {
    title: layer.title,
    status: layer.status,
    optimization_goal: layer.optimization_goal,
    baseline_ref: layer.baseline_ref,
    created_at: layer.created_at || serverTimestamp(),
  })
}

export async function getLayers(uid: string, projectId: string): Promise<DesignProposal[]> {
  const snap = await getDocs(layersCol(uid, projectId))
  return snap.docs.map((d) => ({
    id: d.id,
    ...d.data(),
    diff: { operations: [] },
  } as unknown as DesignProposal))
}

export async function deleteLayer(uid: string, projectId: string, layerId: string) {
  await deleteDoc(doc(layersCol(uid, projectId), layerId))
}

// ── Components ────────────────────────────────────────────────────────────────

export async function saveComponent(uid: string, projectId: string, layerId: string, component: ArchComponent) {
  await setDoc(doc(componentsCol(uid, projectId), component.id), {
    ...component,
    layer_id: layerId,
  })
}

export async function saveComponents(uid: string, projectId: string, layerId: string, components: ArchComponent[]) {
  const batch = writeBatch(db)
  for (const comp of components) {
    batch.set(doc(componentsCol(uid, projectId), comp.id), {
      ...comp,
      layer_id: layerId,
    })
  }
  await batch.commit()
}

export async function getComponents(uid: string, projectId: string, layerId: string): Promise<ArchComponent[]> {
  const snap = await getDocs(componentsCol(uid, projectId))
  return snap.docs
    .map((d) => d.data() as ArchComponent & { layer_id: string })
    .filter((c) => c.layer_id === layerId)
}

export async function deleteComponent(uid: string, projectId: string, componentId: string) {
  await deleteDoc(doc(componentsCol(uid, projectId), componentId))
}

// ── Relations ─────────────────────────────────────────────────────────────────

export async function saveRelations(uid: string, projectId: string, layerId: string, relations: ArchRelation[]) {
  const batch = writeBatch(db)
  for (const rel of relations) {
    batch.set(doc(relationsCol(uid, projectId), rel.id), {
      ...rel,
      layer_id: layerId,
    })
  }
  await batch.commit()
}

export async function getRelations(uid: string, projectId: string, layerId: string): Promise<ArchRelation[]> {
  const snap = await getDocs(relationsCol(uid, projectId))
  return snap.docs
    .map((d) => d.data() as ArchRelation & { layer_id: string })
    .filter((r) => r.layer_id === layerId)
}

export async function deleteRelation(uid: string, projectId: string, relationId: string) {
  await deleteDoc(doc(relationsCol(uid, projectId), relationId))
}

// ── Positions ─────────────────────────────────────────────────────────────────

export async function savePositions(uid: string, projectId: string, positions: Record<string, { x: number; y: number }>) {
  const batch = writeBatch(db)
  for (const [nodeId, pos] of Object.entries(positions)) {
    batch.set(doc(positionsCol(uid, projectId), nodeId), pos)
  }
  await batch.commit()
}

export async function getPositions(uid: string, projectId: string): Promise<Record<string, { x: number; y: number }>> {
  const snap = await getDocs(positionsCol(uid, projectId))
  const result: Record<string, { x: number; y: number }> = {}
  snap.docs.forEach((d) => {
    result[d.id] = d.data() as { x: number; y: number }
  })
  return result
}

export async function saveNodePosition(uid: string, projectId: string, nodeId: string, pos: { x: number; y: number }) {
  await setDoc(doc(positionsCol(uid, projectId), nodeId), pos)
}

export async function deleteNodePosition(uid: string, projectId: string, nodeId: string) {
  await deleteDoc(doc(positionsCol(uid, projectId), nodeId))
}

// ── Simulations ───────────────────────────────────────────────────────────────

export async function saveSimulation(uid: string, projectId: string, result: SimulationResult) {
  await setDoc(doc(simulationsCol(uid, projectId), result.job_id), {
    ...result,
    saved_at: serverTimestamp(),
  })
}

export async function getSimulations(uid: string, projectId: string, maxResults = 10): Promise<SimulationResult[]> {
  const q = query(simulationsCol(uid, projectId), orderBy('saved_at', 'desc'), limit(maxResults))
  const snap = await getDocs(q)
  return snap.docs.map((d) => d.data() as SimulationResult)
}

// ── Full project save/load (bulk operations) ──────────────────────────────────

export interface FullProjectData {
  name: string
  baseline_ref: string
  layers: DesignProposal[]
  components: Record<string, ArchComponent[]>    // layerId -> components
  relations: Record<string, ArchRelation[]>      // layerId -> relations
  positions: Record<string, { x: number; y: number }>
}

export async function saveFullProject(uid: string, projectId: string, data: FullProjectData) {
  // Save project metadata
  await saveProject(uid, projectId, data.name, data.baseline_ref)

  // Save layers
  for (const layer of data.layers) {
    await saveLayer(uid, projectId, layer)
  }

  // Save components per layer
  for (const [layerId, comps] of Object.entries(data.components)) {
    if (comps.length > 0) {
      await saveComponents(uid, projectId, layerId, comps)
    }
  }

  // Save relations per layer
  for (const [layerId, rels] of Object.entries(data.relations)) {
    if (rels.length > 0) {
      await saveRelations(uid, projectId, layerId, rels)
    }
  }

  // Save positions
  if (Object.keys(data.positions).length > 0) {
    await savePositions(uid, projectId, data.positions)
  }
}

export async function loadFullProject(uid: string, projectId: string): Promise<FullProjectData | null> {
  const projSnap = await getDoc(userProjectRef(uid, projectId))
  if (!projSnap.exists()) return null

  const projData = projSnap.data()
  const layers = await getLayers(uid, projectId)
  const positions = await getPositions(uid, projectId)

  const components: Record<string, ArchComponent[]> = {}
  const relations: Record<string, ArchRelation[]> = {}

  for (const layer of layers) {
    components[layer.id] = await getComponents(uid, projectId, layer.id)
    relations[layer.id] = await getRelations(uid, projectId, layer.id)
  }

  return {
    name: projData.name || 'Untitled',
    baseline_ref: projData.baseline_ref || '',
    layers,
    components,
    relations,
    positions,
  }
}
