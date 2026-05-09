/**
 * Simulation store — tracks active simulation jobs, results and events.
 * All result data comes from the backend; no frontend scoring or veto logic.
 */

import { create } from 'zustand'
import type { SimulationResult, SimulationEvent } from '@/generated/simulation-result.types'
import type { OptimizationGoal } from '@/generated/isa.types'

export type JobStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface SimulationJob {
  jobId: string
  layerIds: string[]
  optimizationGoal: OptimizationGoal
  status: JobStatus
  startedAt: string
  completedAt: string | null
  result: SimulationResult | null
  events: SimulationEvent[]
  error: string | null
}

interface SimulationState {
  // Active jobs keyed by jobId
  jobs: Record<string, SimulationJob>

  // Currently viewed job (shown in panels)
  activeJobId: string | null

  // Version compatibility (Section 7.1)
  backendCompatible: boolean | null
  compatibilityWarning: string | null
  setCompatibility: (compatible: boolean, warning?: string) => void

  // Job management
  createJob: (jobId: string, layerIds: string[], goal: OptimizationGoal) => void
  updateJobStatus: (jobId: string, status: JobStatus) => void
  setJobResult: (jobId: string, result: SimulationResult) => void
  appendJobEvent: (jobId: string, event: SimulationEvent) => void
  setJobError: (jobId: string, error: string) => void
  setActiveJob: (jobId: string | null) => void

  // UI panel visibility
  openPanels: Set<string>
  togglePanel: (panelId: string) => void
  isPanelOpen: (panelId: string) => boolean
}

const DEFAULT_PANELS = new Set(['inspector', 'simulation-control'])

export const useSimulationStore = create<SimulationState>((set, get) => ({
  jobs: {},
  activeJobId: null,
  backendCompatible: null,
  compatibilityWarning: null,

  setCompatibility: (compatible, warning) =>
    set({ backendCompatible: compatible, compatibilityWarning: warning ?? null }),

  createJob: (jobId, layerIds, optimizationGoal) =>
    set((s) => ({
      jobs: {
        ...s.jobs,
        [jobId]: {
          jobId,
          layerIds,
          optimizationGoal,
          status: 'pending',
          startedAt: new Date().toISOString(),
          completedAt: null,
          result: null,
          events: [],
          error: null,
        },
      },
      activeJobId: jobId,
    })),

  updateJobStatus: (jobId, status) =>
    set((s) => {
      const job = s.jobs[jobId]
      if (!job) return {}
      return {
        jobs: {
          ...s.jobs,
          [jobId]: {
            ...job,
            status,
            completedAt: ['completed', 'failed', 'cancelled'].includes(status)
              ? new Date().toISOString()
              : job.completedAt,
          },
        },
      }
    }),

  setJobResult: (jobId, result) =>
    set((s) => {
      const job = s.jobs[jobId]
      if (!job) return {}
      return {
        jobs: {
          ...s.jobs,
          [jobId]: { ...job, result, status: 'completed', completedAt: new Date().toISOString() },
        },
      }
    }),

  appendJobEvent: (jobId, event) =>
    set((s) => {
      const job = s.jobs[jobId]
      if (!job) return {}
      return {
        jobs: {
          ...s.jobs,
          [jobId]: { ...job, events: [...job.events, event] },
        },
      }
    }),

  setJobError: (jobId, error) =>
    set((s) => {
      const job = s.jobs[jobId]
      if (!job) return {}
      return {
        jobs: {
          ...s.jobs,
          [jobId]: { ...job, error, status: 'failed', completedAt: new Date().toISOString() },
        },
      }
    }),

  setActiveJob: (jobId) => set({ activeJobId: jobId }),

  openPanels: DEFAULT_PANELS,
  togglePanel: (panelId) =>
    set((s) => {
      const next = new Set(s.openPanels)
      if (next.has(panelId)) {
        next.delete(panelId)
      } else {
        next.add(panelId)
      }
      return { openPanels: next }
    }),
  isPanelOpen: (panelId) => get().openPanels.has(panelId),
}))
