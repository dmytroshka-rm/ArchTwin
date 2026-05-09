/**
 * BlastRadiusOverlay — Section 8.4
 * Floats above the canvas; highlights impacted components without
 * changing their edit state.  Tier-1 components get stronger visual emphasis.
 * Shows distance, impact_score, and mitigation hints grouped by role.
 */

import { useState } from 'react'
import clsx from 'clsx'
import type { BlastRadiusSummary } from '@/generated/simulation-result.types'
import type { TierLevel } from '@/generated/isa.types'

interface Props {
  blastRadius: BlastRadiusSummary
}

const TIER_BADGE: Record<TierLevel, string> = {
  tier_1:    'bg-tier-1/20 text-tier-1 border border-tier-1/40',
  standard:  'bg-tier-standard/20 text-tier-standard border border-tier-standard/40',
  auxiliary: 'bg-tier-auxiliary/20 text-tier-auxiliary border border-tier-auxiliary/40',
}

export function BlastRadiusOverlay({ blastRadius }: Props) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="absolute bottom-4 left-4 w-72 bg-canvas-surface/95 backdrop-blur border border-canvas-border rounded-lg shadow-xl z-10 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-3 py-2 border-b border-canvas-border hover:bg-canvas-border/20"
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
            Blast Radius
          </span>
          {blastRadius.high_risk_count > 0 && (
            <span className="bg-tier-1/20 text-tier-1 border border-tier-1/40 text-[10px] font-mono px-1.5 rounded">
              {blastRadius.high_risk_count} high-risk
            </span>
          )}
        </div>
        <span className="text-slate-500 text-xs">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="p-2 flex flex-col gap-1 max-h-64 overflow-y-auto">
          {/* Summary row */}
          <div className="flex gap-3 text-[10px] text-slate-500 px-1 pb-1 border-b border-canvas-border/40">
            <span>Total: <strong className="text-slate-300">{blastRadius.total_impacted}</strong></span>
            <span>Tier-1: <strong className="text-tier-1">{blastRadius.tier_1_count}</strong></span>
          </div>

          {/* Component list */}
          {blastRadius.components.map((comp) => (
            <div
              key={comp.id}
              className={clsx(
                'rounded-md px-2 py-1.5 border',
                comp.tier === 'tier_1'
                  ? 'border-tier-1/30 bg-tier-1/5'
                  : comp.tier === 'standard'
                  ? 'border-tier-standard/20 bg-tier-standard/5'
                  : 'border-canvas-border/40 bg-canvas-border/10',
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-xs text-slate-200 truncate" title={comp.id}>
                  {comp.name ?? comp.id}
                </span>
                <span className={clsx('text-[9px] font-mono px-1 rounded shrink-0', TIER_BADGE[comp.tier])}>
                  {comp.tier.replace('_', '-')}
                </span>
              </div>

              <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                <span className="text-slate-500">d={comp.distance}</span>
                <span className={clsx(
                  'font-mono',
                  comp.impact_score >= 0.7 ? 'text-status-fail' :
                  comp.impact_score >= 0.4 ? 'text-status-warn' :
                  'text-slate-400',
                )}>
                  impact {comp.impact_score.toFixed(2)}
                </span>
              </div>

              {comp.risk && (
                <div className="text-[10px] text-slate-500 mt-0.5 truncate" title={comp.risk}>
                  {comp.risk}
                </div>
              )}

              {/* Mitigation hints grouped by role */}
              {comp.mitigation_hints && Object.keys(comp.mitigation_hints).length > 0 && (
                <MitigationHints hints={comp.mitigation_hints} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MitigationHints({ hints }: { hints: Record<string, string[]> }) {
  return (
    <div className="mt-1 flex flex-col gap-0.5">
      {Object.entries(hints).map(([role, actions]) => (
        <div key={role}>
          <span className="text-[9px] uppercase tracking-widest text-slate-600">{role}</span>
          {actions.map((action, i) => (
            <div key={i} className="text-[10px] text-slate-400 pl-2">• {action}</div>
          ))}
        </div>
      ))}
    </div>
  )
}
