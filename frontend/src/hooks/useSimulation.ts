/**
 * useSimulation — runs a simulation job and streams real-time events.
 * Connects to backend SSE stream for live reviewer progress.
 */

import { useCallback, useEffect, useRef } from 'react'
import { simulationApi } from '@/api/endpoints'
import { useSimulationStore } from '@/store/simulationStore'
import type { SimulationRequest, SimulationEvent } from '@/generated/simulation-result.types'

export function useSimulation() {
  const {
    createJob,
    updateJobStatus,
    setJobResult,
    appendJobEvent,
    setJobError,
    setActiveJob,
    jobs,
    activeJobId,
  } = useSimulationStore()

  const eventSourceRef = useRef<EventSource | null>(null)

  const closeStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  // Clean up on unmount
  useEffect(() => closeStream, [closeStream])

  const startSimulation = useCallback(
    async (req: SimulationRequest) => {
      const { job_id } = await simulationApi.start(req)

      createJob(job_id, req.proposal_refs, req.optimization_goal)
      setActiveJob(job_id)

      // Open SSE stream for real-time events
      closeStream()
      const es = new EventSource(`/api/simulations/${job_id}/stream`)
      eventSourceRef.current = es

      es.addEventListener('message', (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data as string) as SimulationEvent
          appendJobEvent(job_id, event)

          if (event.event === 'simulation.completed') {
            updateJobStatus(job_id, 'completed')
            // Fetch the full result
            simulationApi.getResult(job_id).then((result) => {
              setJobResult(job_id, result)
            }).catch((err: unknown) => {
              setJobError(job_id, String(err))
            })
            closeStream()
          } else if (event.event === 'simulation.failed') {
            setJobError(job_id, event.payload.reason ?? 'Simulation failed')
            closeStream()
          }
        } catch {
          // ignore parse errors
        }
      })

      es.addEventListener('error', () => {
        // Fallback to polling if SSE fails
        updateJobStatus(job_id, 'running')
        closeStream()
        pollUntilDone(job_id)
      })

      return job_id
    },
    [createJob, setActiveJob, appendJobEvent, updateJobStatus, setJobResult, setJobError, closeStream],
  )

  const pollUntilDone = useCallback(
    (jobId: string) => {
      const interval = setInterval(() => {
        simulationApi.getResult(jobId).then((result) => {
          if (result.status === 'completed' || result.status === 'failed') {
            clearInterval(interval)
            setJobResult(jobId, result)
          }
        }).catch(() => {
          clearInterval(interval)
          setJobError(jobId, 'Polling failed')
        })
      }, 2000)
    },
    [setJobResult, setJobError],
  )

  const cancelSimulation = useCallback(
    async (jobId: string) => {
      await simulationApi.cancel(jobId)
      updateJobStatus(jobId, 'cancelled')
      closeStream()
    },
    [updateJobStatus, closeStream],
  )

  const activeJob = activeJobId ? jobs[activeJobId] : null

  return {
    startSimulation,
    cancelSimulation,
    activeJob,
    allJobs: Object.values(jobs),
  }
}

// ── useVersionHandshake ───────────────────────────────────────────────────

import { useEffect as _useEffect } from 'react'
import { capabilitiesApi } from '@/api/endpoints'

const REQUIRED_AGENT_VERSION = '0.5.3'

export function useVersionHandshake() {
  const { setCompatibility } = useSimulationStore()

  _useEffect(() => {
    capabilitiesApi.get().then((caps) => {
      const compatible = caps.agent_convention_version >= REQUIRED_AGENT_VERSION
      const warning = compatible
        ? undefined
        : `Backend convention v${caps.agent_convention_version} is below required v${REQUIRED_AGENT_VERSION}. Editing disabled.`
      setCompatibility(compatible, warning)
    }).catch(() => {
      setCompatibility(false, 'Could not reach backend. Check API server.')
    })
  }, [setCompatibility])
}
