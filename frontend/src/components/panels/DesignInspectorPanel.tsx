/**
 * DesignInspectorPanel — shows and edits properties of the selected node.
 * All edits are dispatched as CanvasOperations to backend for validation.
 * Section 5.1 — Create or edit a component.
 */

import { useCallback, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { canvasApi } from '@/api/endpoints'
import { nanoid } from '@/components/canvas/nanoid'
import type { ArchComponent } from '@/generated/isa.types'
import type { CanvasOperationStatus } from '@/generated/canvas-operation.types'

interface Props {
  layerId: string | null
  editingBlocked: boolean
}

export function DesignInspectorPanel({ layerId, editingBlocked }: Props) {
  const { selectedNodeIds, addPendingOp, resolvePendingOp, clearSelection } = useCanvasStore()
  const { getComponent, upsertComponent, removeComponent } = useSandboxStore()

  const selectedId = selectedNodeIds[0] ?? null
  const component  = layerId && selectedId ? getComponent(layerId, selectedId) : null

  const [editedName, setEditedName]   = useState<string | null>(null)
  const [editedTech, setEditedTech]   = useState<string | null>(null)
  const [validationMsg, setValidMsg]  = useState<string | null>(null)
  const [validationStatus, setVStatus] = useState<CanvasOperationStatus | null>(null)

  const updateMutation = useMutation({
    mutationFn: async (patch: Partial<ArchComponent>) => {
      if (!layerId || !component) throw new Error('No active layer or component')
      const opId = nanoid()
      addPendingOp({
        id:         opId,
        type:       'update_component',
        status:     'pending_validation',
        created_at: new Date().toISOString(),
        payload:    { component_id: component.id, layer_id: layerId, patch },
      })
      const result = await canvasApi.validateOperation({
        type:    'update_component',
        payload: { component_id: component.id, layer_id: layerId, patch },
      })
      resolvePendingOp(opId, result.status, result.warnings.join('; '))
      return result
    },
    onSuccess: (result) => {
      setVStatus(result.status)
      setValidMsg(result.warnings.join(' ') || null)
      if (result.status === 'valid' && result.normalized && layerId) {
        upsertComponent(layerId, result.normalized as ArchComponent)
      }
    },
    onError: () => {
      setVStatus('invalid')
      setValidMsg('Backend validation failed')
    },
  })

  const commitEdit = useCallback(() => {
    if (!component || editingBlocked) return
    const patch: Partial<ArchComponent> = {}
    if (editedName !== null)  patch.name       = editedName
    if (editedTech !== null)  patch.technology  = editedTech
    if (Object.keys(patch).length > 0) {
      updateMutation.mutate(patch)
    }
    setEditedName(null)
    setEditedTech(null)
  }, [component, editedName, editedTech, editingBlocked, updateMutation])

  const handleDelete = useCallback(() => {
    if (!layerId || !component || editingBlocked) return
    removeComponent(layerId, component.id)
    clearSelection()
  }, [layerId, component, editingBlocked, removeComponent, clearSelection])

  if (!component) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-600 text-xs p-4 text-center">
        Select a component on the canvas to inspect
      </div>
    )
  }

  return (
    <div className="flex flex-col text-sm">
      <PanelHeader title="Inspector" />

      {/* Validation status */}
      {validationStatus && (
        <div className={clsx(
          'mx-3 mt-2 text-[11px] rounded px-2 py-1',
          validationStatus === 'valid'   ? 'bg-status-pass/10 text-status-pass' :
          validationStatus === 'blocked' ? 'bg-status-blocked/10 text-status-blocked' :
          validationStatus === 'requires_adr' ? 'bg-status-info/10 text-status-info' :
          'bg-status-fail/10 text-status-fail',
        )}>
          {validationStatus === 'valid' ? '✓ Valid' : `⚠ ${validationStatus.replace('_', ' ')}`}
          {validationMsg && <span className="block text-[10px] mt-0.5 opacity-80">{validationMsg}</span>}
        </div>
      )}

      {/* Properties */}
      <div className="p-3 flex flex-col gap-2">
        <Field label="ID">
          <span className="font-mono text-[11px] text-slate-400 break-all">{component.id}</span>
        </Field>

        <Field label="Name">
          <input
            className={clsx(
              'w-full bg-canvas-bg border rounded px-2 py-1 text-xs',
              editingBlocked ? 'opacity-50 cursor-not-allowed border-canvas-border' : 'border-canvas-border focus:border-canvas-accent outline-none',
            )}
            value={editedName ?? component.name}
            disabled={editingBlocked}
            onChange={(e) => setEditedName(e.target.value)}
            onBlur={commitEdit}
          />
        </Field>

        <Field label="Type">
          <span className="font-mono text-xs text-slate-300">{component.type}</span>
        </Field>

        <Field label="Technology">
          <input
            className={clsx(
              'w-full bg-canvas-bg border rounded px-2 py-1 text-xs',
              editingBlocked ? 'opacity-50 cursor-not-allowed border-canvas-border' : 'border-canvas-border focus:border-canvas-accent outline-none',
            )}
            value={editedTech ?? (component.technology ?? '')}
            placeholder="e.g. postgresql, redis, fastapi…"
            disabled={editingBlocked}
            onChange={(e) => setEditedTech(e.target.value)}
            onBlur={commitEdit}
          />
        </Field>

        <Field label="Tier">
          <TierBadge tier={component.tier} />
        </Field>

        <Field label="Data Classification">
          <span className="font-mono text-xs text-slate-300">{component.data_classification ?? '—'}</span>
        </Field>

        {/* Observed metrics */}
        {component.observed_metrics && (
          <div className="mt-1">
            <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-1">Observed Metrics</div>
            <div className="flex flex-col gap-0.5">
              {component.observed_metrics.p99_latency_ms !== undefined && (
                <MetricRow label="p99 latency" value={`${component.observed_metrics.p99_latency_ms}ms`} />
              )}
              {component.observed_metrics.requests_per_second !== undefined && (
                <MetricRow label="RPS" value={String(component.observed_metrics.requests_per_second)} />
              )}
              {component.observed_metrics.cache_hit_ratio !== undefined && (
                <MetricRow label="CHR" value={`${(component.observed_metrics.cache_hit_ratio * 100).toFixed(1)}%`} />
              )}
              {component.observed_metrics.last_updated && (
                <MetricRow
                  label="updated"
                  value={new Date(component.observed_metrics.last_updated).toLocaleString()}
                  warn={isStale(component.observed_metrics.last_updated)}
                />
              )}
            </div>
          </div>
        )}

        {/* Delete button */}
        {!editingBlocked && (
          <div className="mt-4 pt-3 border-t border-canvas-border">
            <button
              onClick={handleDelete}
              className="w-full py-2 rounded-md border border-status-fail/40 text-status-fail text-xs hover:bg-status-fail/10 transition-colors"
            >
              Delete Component
            </button>
            <p className="text-[10px] text-slate-600 mt-1 text-center">
              Or select and press Delete / Backspace
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────

function PanelHeader({ title }: { title: string }) {
  return (
    <div className="px-3 py-2 border-b border-canvas-border">
      <span className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">{title}</span>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-widest text-slate-600">{label}</span>
      {children}
    </div>
  )
}

function TierBadge({ tier }: { tier?: string }) {
  const colors: Record<string, string> = {
    tier_1:    'text-tier-1 bg-tier-1/10',
    standard:  'text-tier-standard bg-tier-standard/10',
    auxiliary: 'text-tier-auxiliary bg-tier-auxiliary/10',
  }
  const style = tier ? (colors[tier] ?? '') : ''
  return (
    <span className={clsx('text-[11px] font-mono px-1.5 py-0.5 rounded w-fit', style)}>
      {tier ?? 'unset'}
    </span>
  )
}

function MetricRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex justify-between text-[11px]">
      <span className="text-slate-500">{label}</span>
      <span className={clsx('font-mono', warn ? 'text-status-warn' : 'text-slate-300')}>{value}</span>
    </div>
  )
}

function isStale(isoDate: string): boolean {
  const ageHours = (Date.now() - new Date(isoDate).getTime()) / 3_600_000
  return ageHours > 24
}
