/**
 * C4 Node — visual hierarchy by tier, state, and risk.
 *
 * Visual rules:
 *   - Selection: blue/violet ring (NEVER red)
 *   - Tier-1: bold border + larger visual weight
 *   - Sandbox change: dashed purple border
 *   - Blocked: red border + veto icon
 *   - Blast impact: amber glow
 *   - Baseline stable: muted, calm border
 */

import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import clsx from 'clsx'
import type { ArchComponent } from '@/generated/isa.types'

export type C4NodeData = ArchComponent & {
  label: string
  isBlastImpacted?: boolean
  impactScore?: number
  isSandboxChange?: boolean
  isBlocked?: boolean
  validationStatus?: 'valid' | 'invalid' | 'blocked' | 'pending_validation' | 'requires_adr'
  editingBlocked?: boolean
  [key: string]: unknown
}

const TYPE_ICON: Record<string, string> = {
  system:          '⬡',
  container:       '▣',
  component:       '◈',
  data_store:      '⛁',
  queue:           '⇶',
  gateway:         '◇',
  external_system: '☁',
  cache:           '⚡',
  service:         '◆',
  storage:         '⛁',
}

interface NodeProps {
  data: C4NodeData
  selected: boolean
}

export const C4NodeBase = memo(function C4NodeBase({ data, selected }: NodeProps) {
  const tier = data.tier ?? 'standard'
  const isTier1 = tier === 'tier_1'
  const isAuxiliary = tier === 'auxiliary'
  const icon = TYPE_ICON[data.type] ?? '◆'

  // Determine border style based on state (priority order)
  const borderClass =
    data.isBlocked
      ? 'border-red-500 border-2'                           // Blocked = red (only valid use of red)
      : data.isSandboxChange
      ? 'border-purple-500 border-dashed'                   // Sandbox change = purple dashed
      : data.isBlastImpacted
      ? 'border-amber-500/70'                               // Blast impact = amber
      : isTier1
      ? 'border-slate-400'                                  // Tier-1 = prominent
      : isAuxiliary
      ? 'border-slate-700'                                  // Auxiliary = subtle
      : 'border-slate-600'                                  // Standard = calm

  return (
    <div
      className={clsx(
        'relative rounded-lg border bg-canvas-surface transition-all',
        isTier1 ? 'min-w-[180px] max-w-[240px] px-3.5 py-2.5' : 'min-w-[150px] max-w-[200px] px-3 py-2',
        borderClass,
        // Selection = blue/violet ring (NEVER red)
        selected && 'ring-2 ring-blue-500/80 shadow-[0_0_12px_rgba(79,110,247,0.3)]',
        // Blast radius glow
        data.isBlastImpacted && !selected && 'shadow-[0_0_8px_rgba(245,158,11,0.3)]',
        // Disabled state
        data.editingBlocked && 'opacity-50 cursor-not-allowed',
      )}
    >
      {/* Handles */}
      <Handle type="target" position={Position.Top}    className="!bg-slate-500 !border-slate-600 !w-2 !h-2" />
      <Handle type="source" position={Position.Bottom} className="!bg-slate-500 !border-slate-600 !w-2 !h-2" />
      <Handle type="target" position={Position.Left}   className="!bg-slate-500 !border-slate-600 !w-2 !h-2" />
      <Handle type="source" position={Position.Right}  className="!bg-slate-500 !border-slate-600 !w-2 !h-2" />

      {/* Header row: icon + type + tier badge */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className={clsx('text-xs', isTier1 ? 'text-slate-300' : 'text-slate-500')}>{icon}</span>
        <span className="text-[9px] uppercase tracking-widest text-slate-500 font-mono flex-1">
          {data.type.replace('_', ' ')}
        </span>
        {isTier1 && (
          <span className="text-[8px] font-bold bg-amber-500/20 text-amber-400 px-1 rounded">T1</span>
        )}
        {data.isBlocked && (
          <span className="text-[9px] text-red-400">✕</span>
        )}
      </div>

      {/* Name */}
      <div
        className={clsx(
          'leading-tight truncate',
          isTier1 ? 'text-sm font-bold text-slate-100' : 'text-xs font-semibold text-slate-200',
        )}
        title={data.name}
      >
        {data.name}
      </div>

      {/* Technology */}
      {data.technology && (
        <div className="text-[10px] text-slate-500 font-mono mt-0.5 truncate">
          {data.technology}
        </div>
      )}

      {/* Blast radius indicator */}
      {data.isBlastImpacted && data.impactScore !== undefined && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-amber-400 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          impact {(data.impactScore as number).toFixed(2)}
        </div>
      )}

      {/* Blocked veto badge */}
      {data.isBlocked && (
        <div className="mt-1 text-[9px] bg-red-500/15 text-red-400 rounded px-1.5 py-0.5 border border-red-500/30">
          BLOCKED — veto active
        </div>
      )}

      {/* Sandbox change indicator */}
      {data.isSandboxChange && !data.isBlocked && (
        <div className="mt-1 text-[9px] bg-purple-500/15 text-purple-400 rounded px-1.5 py-0.5 border border-purple-500/30">
          proposed change
        </div>
      )}
    </div>
  )
})
