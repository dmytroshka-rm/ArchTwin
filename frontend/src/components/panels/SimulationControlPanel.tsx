/**
 * SimulationControlPanel — triggers simulations and shows live progress.
 * Section 5.3 (what-if comparison), Section 6.2 (simulation request).
 * No cost/security logic here — purely a UI for invoking the backend.
 */

import { useCallback, useState } from 'react'
import clsx from 'clsx'
import { useSandboxStore } from '@/store/sandboxStore'
import { useSimulation } from '@/hooks/useSimulation'
import type { OptimizationGoal } from '@/generated/isa.types'
import type { SimulationEvent } from '@/generated/simulation-result.types'

const GOALS: { value: OptimizationGoal; label: string; description: string }[] = [
  { value: 'balanced',           label: 'Balanced',         description: 'Equal weight on all factors' },
  { value: 'cost_efficiency',    label: 'Cost Efficiency',  description: 'Minimise TCO and egress costs' },
  { value: 'max_reliability',    label: 'Max Reliability',  description: 'Maximise uptime and fault tolerance' },
  { value: 'minimal_complexity', label: 'Min Complexity',   description: 'Reduce operational complexity' },
]

interface Props {
  editingBlocked: boolean
}

export function SimulationControlPanel({ editingBlocked }: Props) {
  const { comparedLayerIds, baselineRef } = useSandboxStore()
  const { activeJob, cancelSimulation, startSimulation } = useSimulation()

  const [goal, setGoal] = useState<OptimizationGoal>('balanced')
  const [includeBlast, setIncludeBlast] = useState(true)

  const isRunning = activeJob?.status === 'running' || activeJob?.status === 'pending'
  const canRun    = !editingBlocked && !isRunning && comparedLayerIds.length > 0 && !!baselineRef

  const handleRun = useCallback(async () => {
    if (!canRun || !baselineRef) return
    await startSimulation({
      baseline_ref:          baselineRef,
      proposal_refs:         comparedLayerIds,
      optimization_goal:     goal,
      reviewers:             ['cost', 'performance', 'security'],
      include_blast_radius:  includeBlast,
      include_calibration:   true,
      freshness_policy: {
        warn_after_hours:                      24,
        exploratory_after_days:                7,
        block_final_decision_below_confidence: 0.65,
      },
    })
  }, [canRun, baselineRef, comparedLayerIds, goal, includeBlast, startSimulation])

  return (
    <div className="flex flex-col text-sm">
      <PanelHeader title="Simulation" />

      <div className="p-3 flex flex-col gap-3">
        {/* Layer selection summary */}
        <div>
          <Label>Layers to simulate</Label>
          {comparedLayerIds.length === 0 ? (
            <p className="text-[11px] text-slate-500">
              Select layers to compare from the layer bar (click ⇄ on a layer).
            </p>
          ) : (
            <div className="flex flex-wrap gap-1 mt-1">
              {comparedLayerIds.map((id) => (
                <span key={id} className="text-[10px] font-mono bg-canvas-border/60 text-slate-300 rounded px-1.5 py-0.5">
                  {id.slice(-8)}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Optimization Goal */}
        <div>
          <Label>Optimization Goal</Label>
          <div className="flex flex-col gap-1 mt-1">
            {GOALS.map((g) => (
              <button
                key={g.value}
                onClick={() => setGoal(g.value)}
                className={clsx(
                  'text-left rounded-md border px-2.5 py-1.5 transition-colors',
                  goal === g.value
                    ? 'border-canvas-accent bg-canvas-accent/10 text-canvas-accent'
                    : 'border-canvas-border text-slate-400 hover:border-slate-500',
                )}
              >
                <div className="text-xs font-medium">{g.label}</div>
                <div className="text-[10px] text-slate-500">{g.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Options */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeBlast}
            onChange={(e) => setIncludeBlast(e.target.checked)}
            className="accent-canvas-accent"
          />
          <span className="text-xs text-slate-400">Include Blast Radius analysis</span>
        </label>

        {/* Run / Cancel */}
        {isRunning ? (
          <button
            onClick={() => activeJob && cancelSimulation(activeJob.jobId)}
            className="w-full py-2 rounded-md border border-status-warn text-status-warn text-xs hover:bg-status-warn/10"
          >
            Cancel Simulation
          </button>
        ) : (
          <button
            onClick={handleRun}
            disabled={!canRun}
            className={clsx(
              'w-full py-2 rounded-md text-xs font-semibold transition-colors',
              canRun
                ? 'bg-canvas-accent text-white hover:bg-canvas-accent/80'
                : 'bg-canvas-border/50 text-slate-600 cursor-not-allowed',
            )}
          >
            {editingBlocked ? 'Editing Blocked' :
             comparedLayerIds.length === 0 ? 'Select Layers First' :
             'Run Simulation'}
          </button>
        )}

        {/* Live events feed */}
        {activeJob && activeJob.events.length > 0 && (
          <div>
            <Label>Live Events</Label>
            <div className="mt-1 flex flex-col gap-0.5 max-h-36 overflow-y-auto">
              {activeJob.events.map((ev, i) => (
                <EventRow key={i} event={ev} />
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {activeJob?.error && (
          <div className="bg-status-fail/10 border border-status-fail/30 rounded px-2 py-1.5 text-[11px] text-status-fail">
            {activeJob.error}
          </div>
        )}
      </div>
    </div>
  )
}

function PanelHeader({ title }: { title: string }) {
  return (
    <div className="px-3 py-2 border-b border-canvas-border">
      <span className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">{title}</span>
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-0.5">{children}</div>
  )
}

function EventRow({ event }: { event: SimulationEvent }) {
  const color =
    event.event === 'simulation.veto.triggered' ? 'text-status-fail' :
    event.event === 'simulation.reviewer.completed' ? 'text-status-pass' :
    event.event === 'simulation.completed' ? 'text-fidelity-decision' :
    event.event === 'observed_graph.refresh.required' ? 'text-status-warn' :
    'text-slate-500'

  return (
    <div className={clsx('flex gap-1.5 text-[10px] font-mono', color)}>
      <span>•</span>
      <span className="truncate">
        {event.event}
        {event.payload.reviewer && ` [${event.payload.reviewer}]`}
        {event.payload.gate && ` gate=${event.payload.gate}`}
      </span>
    </div>
  )
}
