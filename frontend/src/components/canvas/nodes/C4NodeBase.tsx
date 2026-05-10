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

import { memo, useState, useCallback, useRef, useEffect } from 'react'
import { Handle, Position } from '@xyflow/react'
import clsx from 'clsx'
import { useSandboxStore } from '@/store/sandboxStore'
import { useCanvasStore } from '@/store/canvasStore'
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

  // View mode annotation data (injected by C4GraphRenderer)
  const viewMode = (data._viewMode as string | undefined) ?? null
  const ann = data._annotation as { cost: { label: string; level: string }; security: { risk: string; external_facing: boolean; has_pii: boolean; crosses_boundary: boolean }; blast_radius: { downstream_count: number; weight: number } } | undefined

  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(data.name)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (data.editingBlocked) return
    setEditValue(data.name)
    setEditing(true)
  }, [data.name, data.editingBlocked])

  const commitRename = useCallback(() => {
    setEditing(false)
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== data.name) {
      const activeLayerId = useCanvasStore.getState().activeLayerId
      if (activeLayerId) {
        useSandboxStore.getState().upsertComponent(activeLayerId, { ...data, name: trimmed } as ArchComponent)
      }
    }
  }, [editValue, data])

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
        'group relative rounded-lg border bg-canvas-surface transition-all',
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
      {/* Handles — larger hit area, visible on hover */}
      <Handle type="target" position={Position.Top} className="!bg-canvas-accent/60 !border-canvas-accent !w-3 !h-3 !-top-1.5 opacity-0 group-hover:opacity-100 hover:!bg-canvas-accent hover:!scale-125 transition-all" />
      <Handle type="source" position={Position.Bottom} className="!bg-canvas-accent/60 !border-canvas-accent !w-3 !h-3 !-bottom-1.5 opacity-0 group-hover:opacity-100 hover:!bg-canvas-accent hover:!scale-125 transition-all" />
      <Handle type="target" position={Position.Left} className="!bg-canvas-accent/60 !border-canvas-accent !w-3 !h-3 !-left-1.5 opacity-0 group-hover:opacity-100 hover:!bg-canvas-accent hover:!scale-125 transition-all" />
      <Handle type="source" position={Position.Right} className="!bg-canvas-accent/60 !border-canvas-accent !w-3 !h-3 !-right-1.5 opacity-0 group-hover:opacity-100 hover:!bg-canvas-accent hover:!scale-125 transition-all" />

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

      {/* Name (double-click to rename) */}
      {editing ? (
        <input
          ref={inputRef}
          className="w-full bg-canvas-bg border border-canvas-accent rounded px-1 py-0.5 text-xs text-slate-200 outline-none"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(false) }}
        />
      ) : (
        <div
          className={clsx(
            'leading-tight truncate cursor-text',
            isTier1 ? 'text-sm font-bold text-slate-100' : 'text-xs font-semibold text-slate-200',
          )}
          title={`${data.name} (double-click to rename)`}
          onDoubleClick={handleDoubleClick}
        >
          {data.name}
        </div>
      )}

      {/* Technology */}
      {data.technology && (
        <div className="text-[10px] text-slate-500 font-mono mt-0.5 truncate">
          {data.technology}
        </div>
      )}

      {/* ── View Mode Annotations ────────────────────────────────────── */}
      {viewMode === 'cost' && ann && (
        <div className={clsx(
          'mt-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded border',
          ann.cost.level === 'high' ? 'text-status-fail bg-status-fail/10 border-status-fail/30' :
          ann.cost.level === 'medium' ? 'text-status-warn bg-status-warn/10 border-status-warn/30' :
          'text-status-pass bg-status-pass/10 border-status-pass/30',
        )}>
          {ann.cost.label}
        </div>
      )}

      {viewMode === 'security' && ann && (
        <div className={clsx(
          'mt-1.5 text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded border',
          ann.security.risk === 'high' ? 'text-status-fail bg-status-fail/10 border-status-fail/30' :
          ann.security.risk === 'medium' ? 'text-status-warn bg-status-warn/10 border-status-warn/30' :
          'text-status-pass bg-status-pass/10 border-status-pass/30',
        )}>
          {ann.security.risk} risk
          {ann.security.external_facing && ' · external'}
          {ann.security.has_pii && ' · PII'}
          {ann.security.crosses_boundary && ' · boundary'}
        </div>
      )}

      {viewMode === 'blast' && ann && ann.blast_radius.weight > 0 && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-amber-400 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          impact {ann.blast_radius.weight.toFixed(1)} · {ann.blast_radius.downstream_count} downstream
        </div>
      )}

      {/* Blast radius indicator (from simulation) */}
      {!viewMode && data.isBlastImpacted && data.impactScore !== undefined && (
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
