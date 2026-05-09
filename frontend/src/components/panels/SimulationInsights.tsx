/**
 * SimulationInsights — floating panel. Round 4:
 *   - More compact in collapsed state
 *   - Shows blocked reason inline
 *   - Collapsible to single line
 */

import { useState } from 'react'
import clsx from 'clsx'
import type { SimulationResult } from '@/generated/simulation-result.types'

interface Props {
  result: SimulationResult
}

export function SimulationInsights({ result }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  const { recommendation, veto_gates, fidelity } = result
  const isBlocked = recommendation?.blocked
  const conf = fidelity.adjusted_confidence
  const mode = fidelity.mode

  const proposalRow = result.trade_off_matrix.find((r) => !r.is_baseline)
  const baseRow = result.trade_off_matrix.find((r) => r.is_baseline)

  // Find which gate blocked
  const blockedGate = Object.entries(veto_gates).find(([, status]) => status === 'fail')

  return (
    <div className="absolute bottom-4 left-4 z-10 w-60">
      {/* Collapsed: single compact line */}
      {collapsed ? (
        <button
          onClick={() => setCollapsed(false)}
          className={clsx(
            'w-full flex items-center gap-2 px-3 py-2 rounded-lg border backdrop-blur-sm text-[11px] font-medium',
            isBlocked
              ? 'bg-red-500/10 border-red-500/30 text-red-400'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
          )}
        >
          <span className={clsx('w-2 h-2 rounded-full shrink-0', isBlocked ? 'bg-red-400' : 'bg-emerald-400')} />
          <span className="flex-1 text-left truncate">
            {isBlocked ? `Blocked · ${blockedGate?.[0] ?? 'veto'} fail` : `Score ${recommendation?.recommendation_score.toFixed(2)}`}
          </span>
          <span className="text-slate-600">▲</span>
        </button>
      ) : (
        <div className={clsx(
          'rounded-lg border backdrop-blur-sm overflow-hidden',
          isBlocked ? 'bg-red-500/5 border-red-500/30' : 'bg-canvas-surface/90 border-canvas-border',
        )}>
          {/* Header */}
          <button
            onClick={() => setCollapsed(true)}
            className={clsx(
              'w-full flex items-center justify-between px-3 py-2',
              isBlocked ? 'text-red-400' : 'text-emerald-400',
            )}
          >
            <div className="flex items-center gap-2">
              <span className={clsx('w-2 h-2 rounded-full', isBlocked ? 'bg-red-400' : 'bg-emerald-400')} />
              <span className="text-[11px] font-semibold">
                {isBlocked ? 'BLOCKED' : 'Simulation Complete'}
              </span>
            </div>
            <span className="text-[10px] text-slate-600">▼</span>
          </button>

          {/* Body */}
          <div className="px-3 pb-3">
            {/* Blocked reason (#2 from review) */}
            {isBlocked && blockedGate && (
              <div className="text-[10px] text-red-400/80 mb-2 bg-red-500/10 rounded px-2 py-1">
                Blocked by: <span className="font-semibold capitalize">{blockedGate[0]} Gate</span>
                <br />
                <span className="text-red-400/60">Score is 0.00 because this veto failed</span>
              </div>
            )}

            {/* Score */}
            {!isBlocked && (
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] text-slate-500">Score</span>
                <span className={clsx(
                  'text-sm font-bold font-mono',
                  (recommendation?.recommendation_score ?? 0) >= 0.7 ? 'text-emerald-400' :
                  (recommendation?.recommendation_score ?? 0) >= 0.4 ? 'text-amber-400' : 'text-red-400',
                )}>
                  {recommendation?.recommendation_score.toFixed(2)}
                </span>
              </div>
            )}

            {/* Metrics row */}
            <div className="grid grid-cols-3 gap-1 mb-2">
              <InsightCell label="Cost" value={proposalRow ? proposalRow.cost_score.toFixed(2) : '—'} delta={proposalRow && baseRow ? proposalRow.cost_score - baseRow.cost_score : undefined} />
              <InsightCell label="Perf" value={proposalRow ? proposalRow.performance_score.toFixed(2) : '—'} delta={proposalRow && baseRow ? proposalRow.performance_score - baseRow.performance_score : undefined} />
              <InsightCell label="Security" value={proposalRow ? proposalRow.security_score.toFixed(2) : '—'} delta={proposalRow && baseRow ? proposalRow.security_score - baseRow.security_score : undefined} />
            </div>

            {/* Veto gates compact */}
            <div className="flex gap-1 flex-wrap mb-2">
              {Object.entries(veto_gates).map(([gate, status]) => (
                <span
                  key={gate}
                  className={clsx(
                    'text-[9px] font-mono px-1.5 py-0.5 rounded',
                    status === 'pass' ? 'bg-emerald-500/15 text-emerald-400' :
                    status === 'fail' ? 'bg-red-500/15 text-red-400' :
                    'bg-amber-500/15 text-amber-400',
                  )}
                >
                  {gate.slice(0, 3)}:{status}
                </span>
              ))}
            </div>

            {/* Confidence + mode explanation (#3 from review) */}
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1 bg-canvas-border rounded-full overflow-hidden">
                <div
                  className={clsx('h-full rounded-full', conf >= 0.8 ? 'bg-emerald-500' : conf >= 0.65 ? 'bg-amber-500' : 'bg-red-500')}
                  style={{ width: `${conf * 100}%` }}
                />
              </div>
              <span className="text-[10px] font-mono text-slate-400">{(conf * 100).toFixed(0)}%</span>
            </div>
            <div className="text-[9px] text-slate-600 mt-1">
              {mode === 'decision_grade'
                ? 'Decision-grade · data fresh · safe to promote'
                : mode === 'exploratory_estimate'
                ? 'Exploratory · data partially stale · not promotable yet'
                : 'Blocked · data too stale for any forecast'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function InsightCell({ label, value, delta }: { label: string; value: string; delta?: number }) {
  return (
    <div className="text-center">
      <div className="text-[9px] text-slate-600">{label}</div>
      <div className="text-[11px] font-mono text-slate-200">{value}</div>
      {delta !== undefined && delta !== 0 && (
        <div className={clsx('text-[9px] font-mono', delta > 0 ? 'text-emerald-400' : 'text-red-400')}>
          {delta > 0 ? '+' : ''}{(delta * 100).toFixed(0)}%
        </div>
      )}
    </div>
  )
}
