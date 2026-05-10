/**
 * DesignInspectorPanel — shows and edits properties of the selected node.
 * All edits are dispatched as CanvasOperations to backend for validation.
 * Section 5.1 — Create or edit a component.
 */

import { useCallback, useState } from 'react'
import clsx from 'clsx'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import type { ArchComponent, ArchRelation } from '@/generated/isa.types'

interface Props {
  layerId: string | null
  editingBlocked: boolean
}

const COMPONENT_TYPES = ['service', 'data_store', 'cache', 'queue', 'gateway', 'external_system'] as const
const TIERS = ['tier_1', 'standard', 'auxiliary'] as const
const DATA_CLASSES = ['public', 'internal', 'confidential', 'restricted'] as const
const RELATION_TYPES = ['synchronous', 'asynchronous', 'data_access', 'streaming', 'batch'] as const
const PROTOCOLS = ['HTTPS', 'gRPC', 'PostgreSQL', 'Redis', 'SQS', 'Kafka', 'WebSocket', 'TCP'] as const

export function DesignInspectorPanel({ layerId, editingBlocked }: Props) {
  const { selectedNodeIds, selectedEdgeIds } = useCanvasStore()
  const { getComponent } = useSandboxStore()

  const selectedNodeId = selectedNodeIds[0] ?? null
  const selectedEdgeId = selectedEdgeIds[0] ?? null
  const component = layerId && selectedNodeId ? getComponent(layerId, selectedNodeId) : null

  // Find selected relation
  const layer = layerId ? useSandboxStore.getState().getLayer(layerId) : undefined
  const relation = selectedEdgeId ? layer?.relations.find((r) => r.id === selectedEdgeId) : null

  if (!component && !relation) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-600 text-xs p-4 text-center">
        <div>
          <div className="text-lg mb-2 opacity-50">⬡</div>
          Select a component or edge<br />on the canvas to inspect and edit
        </div>
      </div>
    )
  }

  if (relation && layerId) {
    return <RelationInspector relation={relation} layerId={layerId} editingBlocked={editingBlocked} />
  }

  if (component && layerId) {
    return <ComponentInspector component={component} layerId={layerId} editingBlocked={editingBlocked} />
  }

  return null
}

// ── Component Inspector ───────────────────────────────────────────────────────

function ComponentInspector({ component, layerId, editingBlocked }: {
  component: ArchComponent; layerId: string; editingBlocked: boolean
}) {
  const { upsertComponent, removeComponent } = useSandboxStore()
  const { clearSelection } = useCanvasStore()

  const update = useCallback((patch: Partial<ArchComponent>) => {
    if (editingBlocked) return
    upsertComponent(layerId, { ...component, ...patch })
  }, [component, layerId, editingBlocked, upsertComponent])

  const handleDelete = useCallback(() => {
    if (editingBlocked) return
    removeComponent(layerId, component.id)
    clearSelection()
  }, [layerId, component.id, editingBlocked, removeComponent, clearSelection])

  return (
    <div className="flex flex-col text-sm">
      <PanelHeader title="Component Inspector" />

      <div className="p-3 flex flex-col gap-3">
        <Field label="Name">
          <EditableInput
            value={component.name}
            disabled={editingBlocked}
            onChange={(v) => update({ name: v })}
          />
        </Field>

        <Field label="Type">
          <SelectField
            value={component.type}
            options={COMPONENT_TYPES}
            disabled={editingBlocked}
            onChange={(v) => update({ type: v as ArchComponent['type'] })}
          />
        </Field>

        <Field label="Technology">
          <EditableInput
            value={component.technology ?? ''}
            placeholder="e.g. postgresql, redis, fastapi…"
            disabled={editingBlocked}
            onChange={(v) => update({ technology: v || undefined })}
          />
        </Field>

        <Field label="Tier">
          <SelectField
            value={component.tier ?? 'standard'}
            options={TIERS}
            disabled={editingBlocked}
            onChange={(v) => update({ tier: v as ArchComponent['tier'] })}
          />
        </Field>

        <Field label="Data Classification">
          <SelectField
            value={component.data_classification ?? 'internal'}
            options={DATA_CLASSES}
            disabled={editingBlocked}
            onChange={(v) => update({ data_classification: v as ArchComponent['data_classification'] })}
          />
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
            </div>
          </div>
        )}

        <Field label="ID">
          <span className="font-mono text-[10px] text-slate-500 break-all select-all">{component.id}</span>
        </Field>

        {/* Delete */}
        {!editingBlocked && (
          <div className="mt-3 pt-3 border-t border-canvas-border">
            <button
              onClick={handleDelete}
              className="w-full py-2 rounded-md border border-status-fail/40 text-status-fail text-xs hover:bg-status-fail/10 transition-colors"
            >
              Delete Component
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Relation Inspector ────────────────────────────────────────────────────────

function RelationInspector({ relation, layerId, editingBlocked }: {
  relation: ArchRelation; layerId: string; editingBlocked: boolean
}) {
  const { upsertRelation, removeRelation } = useSandboxStore()
  const { clearSelection } = useCanvasStore()
  const layer = useSandboxStore.getState().getLayer(layerId)

  const sourceName = layer?.components.find((c) => c.id === relation.source_id)?.name ?? relation.source_id
  const targetName = layer?.components.find((c) => c.id === relation.target_id)?.name ?? relation.target_id

  const update = useCallback((patch: Partial<ArchRelation>) => {
    if (editingBlocked) return
    upsertRelation(layerId, { ...relation, ...patch })
  }, [relation, layerId, editingBlocked, upsertRelation])

  const handleDelete = useCallback(() => {
    if (editingBlocked) return
    removeRelation(layerId, relation.id)
    clearSelection()
  }, [layerId, relation.id, editingBlocked, removeRelation, clearSelection])

  return (
    <div className="flex flex-col text-sm">
      <PanelHeader title="Relation Inspector" />

      <div className="p-3 flex flex-col gap-3">
        <Field label="Source">
          <span className="text-xs text-slate-300 font-medium">{sourceName}</span>
        </Field>

        <Field label="Target">
          <span className="text-xs text-slate-300 font-medium">{targetName}</span>
        </Field>

        <Field label="Type">
          <SelectField
            value={relation.type ?? 'synchronous'}
            options={RELATION_TYPES}
            disabled={editingBlocked}
            onChange={(v) => update({ type: v as ArchRelation['type'] })}
          />
        </Field>

        <Field label="Protocol">
          <SelectField
            value={relation.protocol ?? 'HTTPS'}
            options={PROTOCOLS}
            disabled={editingBlocked}
            onChange={(v) => update({ protocol: v })}
          />
        </Field>

        <Field label="Crosses Trust Boundary">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={(relation as any).crosses_trust_boundary ?? false}
              disabled={editingBlocked}
              onChange={(e) => update({ crosses_trust_boundary: e.target.checked } as any)}
              className="w-3.5 h-3.5 rounded border-canvas-border bg-canvas-bg accent-canvas-accent"
            />
            <span className="text-xs text-slate-400">Yes — crosses external boundary</span>
          </label>
        </Field>

        <Field label="ID">
          <span className="font-mono text-[10px] text-slate-500 break-all select-all">{relation.id}</span>
        </Field>

        {/* Delete */}
        {!editingBlocked && (
          <div className="mt-3 pt-3 border-t border-canvas-border">
            <button
              onClick={handleDelete}
              className="w-full py-2 rounded-md border border-status-fail/40 text-status-fail text-xs hover:bg-status-fail/10 transition-colors"
            >
              Delete Relation
            </button>
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

function MetricRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex justify-between text-[11px]">
      <span className="text-slate-500">{label}</span>
      <span className={clsx('font-mono', warn ? 'text-status-warn' : 'text-slate-300')}>{value}</span>
    </div>
  )
}

function EditableInput({ value, placeholder, disabled, onChange }: {
  value: string; placeholder?: string; disabled: boolean; onChange: (v: string) => void
}) {
  const [local, setLocal] = useState(value)
  // Sync when external value changes (e.g. switching selection)
  if (value !== local && local === '') setLocal(value)

  return (
    <input
      className={clsx(
        'w-full bg-canvas-bg border rounded px-2 py-1.5 text-xs text-slate-200',
        disabled ? 'opacity-50 cursor-not-allowed border-canvas-border' : 'border-canvas-border focus:border-canvas-accent outline-none',
      )}
      value={local}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={() => { if (local !== value) onChange(local) }}
      onKeyDown={(e) => { if (e.key === 'Enter') { e.currentTarget.blur() } }}
    />
  )
}

function SelectField({ value, options, disabled, onChange }: {
  value: string; options: readonly string[]; disabled: boolean; onChange: (v: string) => void
}) {
  return (
    <select
      className={clsx(
        'w-full bg-canvas-bg border rounded px-2 py-1.5 text-xs text-slate-200 appearance-none',
        disabled ? 'opacity-50 cursor-not-allowed border-canvas-border' : 'border-canvas-border focus:border-canvas-accent outline-none cursor-pointer',
      )}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((opt) => (
        <option key={opt} value={opt} className="bg-canvas-surface text-slate-200">
          {opt.replace(/_/g, ' ')}
        </option>
      ))}
    </select>
  )
}
