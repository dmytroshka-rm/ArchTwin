/**
 * ComparePanel — side-by-side comparison of 2+ sandbox layers.
 * Shows component differences, cost deltas, and simulation scores.
 */

import { useSandboxStore } from '@/store/sandboxStore'
import { useSimulationStore } from '@/store/simulationStore'
import clsx from 'clsx'

export function ComparePanel() {
  const { comparedLayerIds, layers } = useSandboxStore()
  const { activeJobId, jobs } = useSimulationStore()
  const activeJob = activeJobId ? jobs[activeJobId] : null

  if (comparedLayerIds.length < 2) {
    return (
      <div className="p-4 text-center">
        <div className="text-lg mb-2 opacity-40">⇄</div>
        <p className="text-[12px] text-slate-500 mb-2">Compare what-if layers</p>
        <p className="text-[11px] text-slate-600">
          Select 2 or more layers for comparison by clicking the ⇄ icon on each layer tab.
        </p>
      </div>
    )
  }

  const comparedLayers = comparedLayerIds
    .map((id) => layers[id])
    .filter(Boolean)

  return (
    <div className="p-3 space-y-4">
      <h3 className="text-[11px] font-bold text-slate-200 uppercase tracking-wider">Layer Comparison</h3>

      {/* Component count comparison */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Components</div>
        <div className="space-y-1">
          {comparedLayers.map((ld) => (
            <div key={ld.proposal.id} className="flex items-center justify-between bg-canvas-bg/50 rounded px-2 py-1.5">
              <span className="text-[11px] text-slate-300 font-medium truncate">{ld.proposal.title}</span>
              <span className="text-[11px] text-slate-400 font-mono">{ld.components.length} nodes</span>
            </div>
          ))}
        </div>
      </div>

      {/* Component diff */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Differences</div>
        <ComponentDiff layers={comparedLayers} />
      </div>

      {/* Simulation scores (if available) */}
      {activeJob?.result && (
        <div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Simulation Scores</div>
          <div className="space-y-1">
            {comparedLayers.map((ld) => {
              const row = activeJob.result?.trade_off_matrix?.find(
                (r) => r.proposal_id === ld.proposal.id
              )
              const score = row?.recommendation_score
              return (
                <div key={ld.proposal.id} className="flex items-center justify-between bg-canvas-bg/50 rounded px-2 py-1.5">
                  <span className="text-[11px] text-slate-300 truncate">{ld.proposal.title}</span>
                  {score !== undefined ? (
                    <span className={clsx(
                      'text-[11px] font-mono font-semibold',
                      score >= 0.7 ? 'text-status-pass' : score > 0 ? 'text-status-warn' : 'text-status-fail',
                    )}>
                      {score === 0 ? 'BLOCKED' : score.toFixed(2)}
                    </span>
                  ) : (
                    <span className="text-[10px] text-slate-600">Not simulated</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Relation comparison */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Relations</div>
        <div className="space-y-1">
          {comparedLayers.map((ld) => (
            <div key={ld.proposal.id} className="flex items-center justify-between bg-canvas-bg/50 rounded px-2 py-1.5">
              <span className="text-[11px] text-slate-300 truncate">{ld.proposal.title}</span>
              <span className="text-[11px] text-slate-400 font-mono">{ld.relations.length} edges</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Component diff helper ─────────────────────────────────────────────────────

function ComponentDiff({ layers }: { layers: { proposal: { id: string; title: string }; components: { id: string; name: string; type: string }[] }[] }) {
  if (layers.length < 2) return null

  const baseComponents = new Set(layers[0].components.map((c) => c.id))
  const allIds = new Set(layers.flatMap((l) => l.components.map((c) => c.id)))

  const added: string[] = []
  const removed: string[] = []
  const shared: string[] = []

  for (const id of allIds) {
    const inBase = baseComponents.has(id)
    const inOthers = layers.slice(1).some((l) => l.components.some((c) => c.id === id))
    if (inBase && inOthers) shared.push(id)
    else if (!inBase && inOthers) added.push(id)
    else if (inBase && !inOthers) removed.push(id)
  }

  // Get names from any layer that has the component
  const getName = (id: string) => {
    for (const l of layers) {
      const c = l.components.find((c) => c.id === id)
      if (c) return c.name
    }
    return id
  }

  if (added.length === 0 && removed.length === 0) {
    return <p className="text-[11px] text-slate-600">No component differences between layers.</p>
  }

  return (
    <div className="space-y-1 text-[11px]">
      {added.map((id) => (
        <div key={id} className="flex items-center gap-1.5 text-status-pass">
          <span>+</span><span>{getName(id)}</span>
        </div>
      ))}
      {removed.map((id) => (
        <div key={id} className="flex items-center gap-1.5 text-status-fail">
          <span>-</span><span>{getName(id)}</span>
        </div>
      ))}
      {shared.length > 0 && (
        <div className="text-slate-600">{shared.length} shared components</div>
      )}
    </div>
  )
}
