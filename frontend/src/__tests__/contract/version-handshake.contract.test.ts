/**
 * Contract tests — version handshake (Section 7.1).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useVersionHandshake } from '@/hooks/useSimulation'
import * as endpointsModule from '@/api/endpoints'
import type { BackendCapabilities } from '@/api/endpoints'
import { useSimulationStore } from '@/store/simulationStore'

function makeCapabilities(version: string): BackendCapabilities {
  return {
    isa_schema_version:                 '1.0.0',
    simulation_result_schema_version:   '1.0.0',
    canvas_event_schema_version:        '1.0.0',
    agent_convention_version:           version,
    supported_goals:                    ['balanced', 'cost_efficiency', 'max_reliability', 'minimal_complexity'],
    supported_reviewers:                ['cost', 'performance', 'security'],
  }
}

describe('useVersionHandshake', () => {
  beforeEach(() => {
    useSimulationStore.setState({ backendCompatible: null, compatibilityWarning: null })
    vi.restoreAllMocks()
  })

  it('sets backendCompatible=true when version >= 0.5.3', async () => {
    vi.spyOn(endpointsModule.capabilitiesApi, 'get').mockResolvedValue(makeCapabilities('0.5.3'))
    renderHook(() => useVersionHandshake())
    await act(async () => { await Promise.resolve() })
    const state = useSimulationStore.getState()
    expect(state.backendCompatible).toBe(true)
    expect(state.compatibilityWarning).toBeNull()
  })

  it('sets backendCompatible=false and warning when version < 0.5.3', async () => {
    vi.spyOn(endpointsModule.capabilitiesApi, 'get').mockResolvedValue(makeCapabilities('0.4.0'))
    renderHook(() => useVersionHandshake())
    await act(async () => { await Promise.resolve() })
    const state = useSimulationStore.getState()
    expect(state.backendCompatible).toBe(false)
    expect(state.compatibilityWarning).toContain('0.4.0')
  })

  it('sets backendCompatible=false when API unreachable', async () => {
    vi.spyOn(endpointsModule.capabilitiesApi, 'get').mockRejectedValue(new Error('Network error'))
    renderHook(() => useVersionHandshake())
    await act(async () => { await Promise.resolve() })
    const state = useSimulationStore.getState()
    expect(state.backendCompatible).toBe(false)
  })
})
