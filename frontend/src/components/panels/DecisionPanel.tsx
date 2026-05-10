/**
 * DecisionPanel — context-aware decision cockpit.
 * Round 2: impact summary, type-specific fields, disabled button reasons, tier tooltips.
 */

import { useCallback, useState } from 'react'
import clsx from 'clsx'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { layerApi } from '@/api/endpoints'
import type { ArchComponent } from '@/generated/isa.types'
import type { SimulationResult } from '@/generated/simulation-result.types'
import type { PromotionArtifacts } from '@/generated/simulation-result.types'

interface Props {
  layerId: string | null
  editingBlocked: boolean
  simulationResult: SimulationResult | null
  onRunSimulation: () => void
}

export function DecisionPanel({ layerId, editingBlocked, simulationResult, onRunSimulation }: Props) {
  const { selectedNodeIds, clearSelection } = useCanvasStore()
  const { getComponent, removeComponent, getLayer } = useSandboxStore()

  const selectedId = selectedNodeIds[0] ?? null
  const component = layerId && selectedId ? getComponent(layerId, selectedId) : null
  const layer = layerId ? getLayer(layerId) : undefined

  const handleDelete = useCallback(() => {
    if (!layerId || !component || editingBlocked) return
    removeComponent(layerId, component.id)
    clearSelection()
  }, [layerId, component, editingBlocked, removeComponent, clearSelection])

  if (!component) {
    return <LayerOverview simulationResult={simulationResult} onRunSimulation={onRunSimulation} />
  }

  const metrics = component.observed_metrics
  const isTier1 = component.tier === 'tier_1'
  const blastEntry = simulationResult?.blast_radius?.components.find((c) => c.id === component.id)

  // Find direct dependencies for impact summary
  const relations = layer?.relations ?? []
  const downstreamIds = relations.filter((r) => r.source_id === component.id).map((r) => r.target_id)
  const upstreamIds = relations.filter((r) => r.target_id === component.id).map((r) => r.source_id)
  const allComponents = layer?.components ?? []
  const downstreamNames = downstreamIds.map((id) => allComponents.find((c) => c.id === id)?.name ?? id.split('.').pop())
  const upstreamNames = upstreamIds.map((id) => allComponents.find((c) => c.id === id)?.name ?? id.split('.').pop())

  // Determine component role
  const role = getComponentRole(component)

  // Whether there are what-if layers
  const hasMultipleLayers = Object.keys(useSandboxStore.getState().layers).length > 1

  return (
    <div className="flex flex-col">
      {/* ── Header ──────────────────────────────────── */}
      <div className="px-4 py-3 border-b border-canvas-border">
        <div className="flex items-center gap-2">
          <h3 className={clsx('font-semibold', isTier1 ? 'text-sm text-slate-100' : 'text-xs text-slate-200')}>
            {component.name}
          </h3>
          {isTier1 && (
            <span className="text-[8px] font-bold bg-amber-500/20 text-amber-400 px-1.5 rounded cursor-help" title="Tier-1: Critical component. Blast radius multiplier: 2.0×">
              T1
            </span>
          )}
          {component.tier === 'auxiliary' && (
            <span className="text-[8px] bg-slate-700 text-slate-500 px-1.5 rounded cursor-help" title="Auxiliary: Non-critical. Blast radius multiplier: 0.5×">
              AUX
            </span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 font-mono mt-0.5">
          {component.technology || component.type} · {component.data_classification || 'unclassified'}
        </div>
        {role && <div className="text-[10px] text-slate-600 mt-0.5">{role}</div>}
      </div>

      <div className="flex flex-col divide-y divide-canvas-border/50 overflow-y-auto">
        {/* ── Impact Summary — visual hierarchy ──────── */}
        <Section title="Impact Summary">
          <div className="flex flex-col gap-2.5">
            {upstreamNames.length > 0 && (
              <div>
                <div className="text-[9px] uppercase tracking-widest text-slate-700 mb-0.5">Receives from</div>
                <div className="text-[11px] text-slate-300 font-medium">{upstreamNames.join(', ')}</div>
              </div>
            )}
            {downstreamNames.length > 0 && (
              <div>
                <div className="text-[9px] uppercase tracking-widest text-slate-700 mb-0.5">Impacts</div>
                <div className="text-xs text-slate-200 font-semibold">{downstreamIds.length} direct {downstreamIds.length === 1 ? 'dependency' : 'dependencies'}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">{downstreamNames.join(', ')}</div>
              </div>
            )}
            {component.type === 'gateway' && (
              <div>
                <div className="text-[9px] uppercase tracking-widest text-slate-700 mb-0.5">Security boundary</div>
                <div className="text-[11px] text-amber-400 font-medium">External-facing entry point</div>
              </div>
            )}
            {blastEntry && (
              <div>
                <div className="text-[9px] uppercase tracking-widest text-slate-700 mb-0.5">Known risk</div>
                <div className="text-[11px] text-amber-400">{blastEntry.risk}</div>
              </div>
            )}
          </div>
        </Section>

        {/* ── Type-Specific Info ────────────────────── */}
        <TypeSpecificSection component={component} />

        {/* ── Live Metrics ──────────────────────────── */}
        {metrics && (
          <Section title="Live Metrics">
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {metrics.p99_latency_ms !== undefined && <MetricCell label="p99 latency" value={`${metrics.p99_latency_ms}ms`} />}
              {metrics.requests_per_second !== undefined && <MetricCell label="RPS" value={String(metrics.requests_per_second)} />}
              {metrics.cache_hit_ratio !== undefined && <MetricCell label="Cache HR" value={`${(metrics.cache_hit_ratio * 100).toFixed(0)}%`} />}
              {metrics.error_rate !== undefined && <MetricCell label="Error rate" value={`${(metrics.error_rate * 100).toFixed(2)}%`} warn={metrics.error_rate > 0.01} />}
            </div>
            {metrics.last_updated && (
              <div className={clsx('text-[10px] mt-2 font-mono', isStale(metrics.last_updated) ? 'text-amber-400' : 'text-slate-600')}>
                {timeAgo(metrics.last_updated)} {isStale(metrics.last_updated) && '⚠ stale — refresh needed'}
              </div>
            )}
          </Section>
        )}

        {/* ── Simulation Readiness ──────────────────── */}
        <Section title="Simulation Readiness">
          <div className="flex flex-col gap-1.5">
            <ReadinessRow
              label="Confidence"
              value={simulationResult ? `${(simulationResult.fidelity.adjusted_confidence * 100).toFixed(0)}%` : 'Pending simulation'}
              status={simulationResult ? (simulationResult.fidelity.adjusted_confidence >= 0.8 ? 'good' : simulationResult.fidelity.adjusted_confidence >= 0.65 ? 'warn' : 'bad') : 'neutral'}
            />
            <ReadinessRow
              label="Data freshness"
              value={metrics?.last_updated ? timeAgo(metrics.last_updated) : 'No metrics'}
              status={metrics?.last_updated ? (isStale(metrics.last_updated) ? 'warn' : 'good') : 'neutral'}
            />
            <ReadinessRow
              label="Technology"
              value={component.technology || 'Not specified'}
              status={component.technology ? 'good' : 'warn'}
            />
          </div>
        </Section>

        {/* ── Risk Summary (if simulation ran) ──────── */}
        {simulationResult && (
          <Section title="Risk Summary">
            <div className="flex flex-col gap-1.5">
              {Object.entries(simulationResult.veto_gates).map(([gate, status]) => (
                <div key={gate} className="flex items-center justify-between">
                  <span className="text-[11px] text-slate-400 capitalize">{gate}</span>
                  <StatusBadge status={status as string} />
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Actions (wired to backend) ──────────── */}
        <ActionsSection
          layerId={layerId}
          editingBlocked={editingBlocked}
          simulationResult={simulationResult}
          hasMultipleLayers={hasMultipleLayers}
          onRunSimulation={onRunSimulation}
          onDelete={handleDelete}
        />
      </div>
    </div>
  )
}

// ── Type-Specific Section ─────────────────────────────────────────────────

function TypeSpecificSection({ component }: { component: ArchComponent }) {
  const type = component.type

  if (type === 'gateway') {
    return (
      <Section title="Gateway Details">
        <div className="flex flex-col gap-1 text-[11px]">
          <InfoRow label="Exposure" value="Public (external-facing)" warn />
          <InfoRow label="Auth" value={component.tags?.includes('rate-limit') ? 'Rate-limited' : 'Unknown'} />
          <InfoRow label="TLS" value="Required (inferred)" />
          <InfoRow label="Downstream" value={`Routes to services`} />
        </div>
      </Section>
    )
  }

  if (type === 'data_store') {
    return (
      <Section title="Data Store Details">
        <div className="flex flex-col gap-1 text-[11px]">
          <InfoRow label="Engine" value={component.technology || 'Unknown'} />
          <InfoRow label="Classification" value={component.data_classification || 'Unset'} warn={!component.data_classification} />
          <InfoRow label="PII" value={component.data_classification === 'restricted' ? 'Contains PII' : component.data_classification === 'confidential' ? 'Possible' : 'Unlikely'} warn={component.data_classification === 'restricted'} />
          {component.tags?.includes('multi-az') && <InfoRow label="HA" value="Multi-AZ enabled" />}
        </div>
      </Section>
    )
  }

  if (type === 'cache') {
    return (
      <Section title="Cache Details">
        <div className="flex flex-col gap-1 text-[11px]">
          <InfoRow label="Engine" value={component.technology || 'Unknown'} />
          <InfoRow label="CHR" value={component.observed_metrics?.cache_hit_ratio ? `${(component.observed_metrics.cache_hit_ratio * 100).toFixed(0)}%` : 'Not measured'} />
          <InfoRow label="Impact" value="Reduces DB load, improves latency" />
        </div>
      </Section>
    )
  }

  if (type === 'queue') {
    return (
      <Section title="Queue Details">
        <div className="flex flex-col gap-1 text-[11px]">
          <InfoRow label="Engine" value={component.technology || 'Unknown'} />
          <InfoRow label="Pattern" value={component.tags?.includes('fifo') ? 'FIFO (ordered)' : 'Standard'} />
          <InfoRow label="Coupling" value="Decouples producer from consumer" />
        </div>
      </Section>
    )
  }

  if (type === 'external_system') {
    return (
      <Section title="External System">
        <div className="flex flex-col gap-1 text-[11px]">
          <InfoRow label="Provider" value={component.technology || component.name} />
          <InfoRow label="Trust" value="Crosses trust boundary" warn />
          {component.data_classification === 'restricted' && <InfoRow label="PCI" value="PCI-scoped" warn />}
          <InfoRow label="Control" value="No direct control — SLA-dependent" />
        </div>
      </Section>
    )
  }

  // Default: service
  return (
    <Section title="Service Details">
      <div className="flex flex-col gap-1 text-[11px]">
        <InfoRow label="Runtime" value={component.technology || 'Unknown'} />
        <InfoRow label="Tier" value={`${component.tier ?? 'standard'} — multiplier ${component.tier === 'tier_1' ? '2.0×' : component.tier === 'auxiliary' ? '0.5×' : '1.0×'}`} />
        {component.data_classification && <InfoRow label="Data" value={component.data_classification} />}
      </div>
    </Section>
  )
}

// ── Layer Overview (no selection) ─────────────────────────────────────────

function LayerOverview({ simulationResult, onRunSimulation }: { simulationResult: SimulationResult | null; onRunSimulation: () => void }) {
  if (!simulationResult) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center gap-4">
        <div className="text-3xl opacity-30">⬡</div>
        <div>
          <p className="text-xs text-slate-400">Select a component to inspect</p>
          <p className="text-[11px] text-slate-600 mt-1">Or run a simulation to see decision insights</p>
        </div>
        <button onClick={onRunSimulation} className="text-xs px-4 py-2 bg-canvas-accent text-white rounded-lg hover:bg-canvas-accent/80">
          Run Simulation
        </button>
      </div>
    )
  }

  const { recommendation, veto_gates, fidelity, required_actions } = simulationResult

  // Find blocking gate for explanation
  const blockedGate = Object.entries(veto_gates).find(([, s]) => s === 'fail')

  // Rank actions by priority
  const allActions = [
    ...(required_actions.architect ?? []).filter(a => a.includes('BLOCK')).map(a => ({ priority: 'blocking' as const, role: 'arch', text: a })),
    ...(required_actions.developer ?? []).filter(a => a.includes('BLOCK')).map(a => ({ priority: 'blocking' as const, role: 'dev', text: a })),
    ...(required_actions.developer ?? []).filter(a => a.includes('Refresh') || a.includes('Trigger')).map(a => ({ priority: 'required' as const, role: 'dev', text: a })),
    ...(required_actions.developer ?? []).filter(a => !a.includes('BLOCK') && !a.includes('Refresh') && !a.includes('Trigger')).map(a => ({ priority: 'recommended' as const, role: 'dev', text: a })),
    ...(required_actions.architect ?? []).filter(a => !a.includes('BLOCK')).map(a => ({ priority: 'recommended' as const, role: 'arch', text: a })),
    ...(required_actions.security_ops ?? []).map(a => ({ priority: 'optional' as const, role: 'sec', text: a })),
  ]

  return (
    <div className="flex flex-col divide-y divide-canvas-border/50">
      {/* Proposal scope (#11) */}
      <Section title="Proposal">
        <div className="text-[11px] text-slate-300">
          {recommendation?.winner ?? 'Current sandbox layer'}
        </div>
        <div className="text-[10px] text-slate-600 mt-0.5">
          Goal: {recommendation?.optimization_goal?.replace('_', ' ') ?? 'balanced'} · Scope: active sandbox layer
        </div>
      </Section>

      {/* Recommendation with explanation (#2) */}
      <Section title="Recommendation">
        <div className={clsx(
          'rounded-lg px-3 py-2.5 border',
          recommendation?.blocked ? 'bg-red-500/10 border-red-500/30' : 'bg-emerald-500/10 border-emerald-500/30',
        )}>
          <div className={clsx('text-xs font-semibold', recommendation?.blocked ? 'text-red-400' : 'text-emerald-400')}>
            {recommendation?.blocked ? 'BLOCKED' : 'RECOMMENDED'}
          </div>
          <div className="text-[11px] text-slate-300 mt-0.5 font-mono">
            Score: {recommendation?.recommendation_score.toFixed(2)}
          </div>
          {/* Score explanation (#2) */}
          {recommendation?.blocked && blockedGate && (
            <div className="text-[10px] text-red-400/80 mt-1.5 bg-red-500/10 rounded px-2 py-1">
              Score is 0.00 because <span className="font-semibold capitalize">{blockedGate[0]}</span> veto failed.
              {blockedGate[0] === 'reliability' && ' Throughput or latency regression detected.'}
              {blockedGate[0] === 'security' && ' Security vulnerability or exposure detected.'}
              {blockedGate[0] === 'compliance' && ' Compliance requirement not met.'}
            </div>
          )}
        </div>
      </Section>

      {/* Veto Gates */}
      <Section title="Veto Gates">
        {Object.entries(veto_gates).map(([gate, status]) => (
          <div key={gate} className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-slate-400 capitalize">{gate}</span>
            <StatusBadge status={status as string} />
          </div>
        ))}
      </Section>

      {/* Confidence with mode explanation (#3) */}
      <Section title="Confidence & Fidelity">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 bg-canvas-border rounded-full overflow-hidden">
            <div
              className={clsx('h-full rounded-full', fidelity.adjusted_confidence >= 0.8 ? 'bg-emerald-500' : fidelity.adjusted_confidence >= 0.65 ? 'bg-amber-500' : 'bg-red-500')}
              style={{ width: `${fidelity.adjusted_confidence * 100}%` }}
            />
          </div>
          <span className="text-[11px] font-mono text-slate-300">{(fidelity.adjusted_confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="text-[10px] mt-1.5">
          {fidelity.mode === 'decision_grade' ? (
            <span className="text-emerald-400">Decision-grade · data fresh · safe to promote</span>
          ) : fidelity.mode === 'exploratory_estimate' ? (
            <span className="text-amber-400">Exploratory estimate · data partially stale · not promotable</span>
          ) : (
            <span className="text-red-400">Blocked · data too stale for any forecast</span>
          )}
        </div>
      </Section>

      {/* Required Actions — ranked by priority (#12) */}
      {allActions.length > 0 && (
        <Section title={`Required Actions (${allActions.length})`}>
          <div className="flex flex-col gap-2">
            {allActions.filter(a => a.priority === 'blocking').length > 0 && (
              <ActionGroup priority="blocking" actions={allActions.filter(a => a.priority === 'blocking')} />
            )}
            {allActions.filter(a => a.priority === 'required').length > 0 && (
              <ActionGroup priority="required" actions={allActions.filter(a => a.priority === 'required')} />
            )}
            {allActions.filter(a => a.priority === 'recommended').length > 0 && (
              <ActionGroup priority="recommended" actions={allActions.filter(a => a.priority === 'recommended')} />
            )}
            {allActions.filter(a => a.priority === 'optional').length > 0 && (
              <ActionGroup priority="optional" actions={allActions.filter(a => a.priority === 'optional')} />
            )}
          </div>
        </Section>
      )}
    </div>
  )
}

// ── Ranked action group ───────────────────────────────────────────────────

function ActionGroup({ priority, actions }: { priority: 'blocking' | 'required' | 'recommended' | 'optional'; actions: { role: string; text: string }[] }) {
  const [expanded, setExpanded] = useState(priority === 'blocking')

  const styles = {
    blocking:    { label: 'BLOCKING', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' },
    required:    { label: 'REQUIRED', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
    recommended: { label: 'RECOMMENDED', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
    optional:    { label: 'OPTIONAL', color: 'text-slate-500', bg: 'bg-slate-700/30', border: 'border-slate-600/30' },
  }
  const s = styles[priority]

  return (
    <div className={clsx('rounded-md border px-2.5 py-1.5', s.bg, s.border)}>
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center justify-between">
        <span className={clsx('text-[9px] font-bold uppercase tracking-wider', s.color)}>
          {s.label} ({actions.length})
        </span>
        <span className="text-[10px] text-slate-600">{expanded ? '▾' : '▸'}</span>
      </button>
      {expanded && (
        <div className="mt-1.5 flex flex-col gap-1">
          {actions.map((a, i) => (
            <RankedActionItem key={i} role={a.role} text={a.text} />
          ))}
        </div>
      )}
    </div>
  )
}

function RankedActionItem({ role, text }: { role: string; text: string }) {
  const color = role === 'dev' ? 'text-blue-400' : role === 'arch' ? 'text-purple-400' : 'text-amber-400'
  // Extract short title from action text
  const shortTitle = text.includes(':') ? text.split(':')[0].replace('BLOCK', '').replace('—', '').trim() : text.slice(0, 50)
  const detail = text.includes(':') ? text.split(':').slice(1).join(':').trim() : ''

  return (
    <div className="text-[10px]">
      <div className="flex gap-1.5 items-start">
        <span className={clsx('shrink-0 uppercase font-bold', color)}>{role}</span>
        <span className="text-slate-300 font-medium">{shortTitle}</span>
      </div>
      {detail && <div className="text-slate-600 ml-7 mt-0.5 line-clamp-2">{detail}</div>}
    </div>
  )
}

// ── Shared UI ─────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3">
      <h4 className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold mb-2">{title}</h4>
      {children}
    </div>
  )
}

function MetricCell({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-slate-600">{label}</div>
      <div className={clsx('text-xs font-mono', warn ? 'text-amber-400' : 'text-slate-200')}>{value}</div>
    </div>
  )
}

function InfoRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-600">{label}</span>
      <span className={clsx('text-right', warn ? 'text-amber-400' : 'text-slate-300')}>{value}</span>
    </div>
  )
}

function ReadinessRow({ label, value, status }: { label: string; value: string; status: 'good' | 'warn' | 'bad' | 'neutral' }) {
  const dot = status === 'good' ? 'bg-emerald-400' : status === 'warn' ? 'bg-amber-400' : status === 'bad' ? 'bg-red-400' : 'bg-slate-600'
  return (
    <div className="flex items-center gap-2">
      <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', dot)} />
      <span className="text-[11px] text-slate-400 flex-1">{label}</span>
      <span className={clsx('text-[11px] font-mono', status === 'neutral' ? 'text-slate-500 italic' : 'text-slate-300')}>{value}</span>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const style = status === 'pass' ? 'text-emerald-400 bg-emerald-500/10' :
                status === 'fail' ? 'text-red-400 bg-red-500/10' :
                status === 'warn' ? 'text-amber-400 bg-amber-500/10' :
                'text-slate-500 bg-slate-700/30'
  return <span className={clsx('text-[10px] font-mono px-1.5 py-0.5 rounded', style)}>{status}</span>
}

function ActionButton({ children, onClick, primary, danger, disabled, disabledReason }: {
  children: React.ReactNode; onClick: () => void; primary?: boolean; danger?: boolean; disabled?: boolean; disabledReason?: string
}) {
  return (
    <div className="relative group">
      <button
        onClick={onClick}
        disabled={disabled}
        className={clsx(
          'w-full text-left text-[11px] px-3 py-2 rounded-md border transition-colors',
          disabled ? 'opacity-50 cursor-not-allowed border-canvas-border text-slate-600' :
          primary ? 'border-canvas-accent/50 text-canvas-accent hover:bg-canvas-accent/10' :
          danger ? 'border-red-500/30 text-red-400 hover:bg-red-500/10' :
          'border-canvas-border text-slate-400 hover:border-slate-500 hover:text-slate-300',
        )}
      >
        {children}
      </button>
      {/* Disabled reason tooltip */}
      {disabled && disabledReason && (
        <div className="absolute left-0 right-0 -bottom-6 text-[9px] text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity text-center">
          {disabledReason}
        </div>
      )}
    </div>
  )
}

// ── Actions Section (wired to backend) ────────────────────────────────────

function ActionsSection({ layerId, editingBlocked, simulationResult, hasMultipleLayers, onRunSimulation, onDelete }: {
  layerId: string | null; editingBlocked: boolean; simulationResult: SimulationResult | null
  hasMultipleLayers: boolean; onRunSimulation: () => void; onDelete: () => void
}) {
  const [promotionResult, setPromotionResult] = useState<PromotionArtifacts | null>(null)
  const [promoting, setPromoting] = useState(false)
  const [promoError, setPromoError] = useState<string | null>(null)

  const handlePromote = useCallback(async () => {
    if (!layerId) return
    setPromoting(true)
    setPromoError(null)
    try {
      const artifacts = await layerApi.promote(layerId)
      setPromotionResult(artifacts)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Promotion failed'
      setPromoError(msg)
    } finally {
      setPromoting(false)
    }
  }, [layerId])

  const handleGenerateADR = useCallback(async () => {
    if (!layerId) return
    setPromoting(true)
    setPromoError(null)
    try {
      const artifacts = await layerApi.promote(layerId)
      setPromotionResult(artifacts)
    } catch (e: unknown) {
      setPromoError(e instanceof Error ? e.message : 'ADR generation failed')
    } finally {
      setPromoting(false)
    }
  }, [layerId])

  return (
    <Section title="Actions">
      <div className="flex flex-col gap-2">
        <ActionButton onClick={onRunSimulation} primary disabled={editingBlocked}>
          Simulate this component
        </ActionButton>
        <ActionButton
          onClick={() => {
            // Select all layers for comparison and switch to Compare tab
            const allLayerIds = Object.keys(useSandboxStore.getState().layers)
            useSandboxStore.getState().setComparedLayers(allLayerIds)
            window.dispatchEvent(new CustomEvent('archtwin:switch-panel', { detail: 'compare' }))
          }}
          disabled={!hasMultipleLayers}
          disabledReason={!hasMultipleLayers ? 'Create a What-if layer first' : undefined}
        >
          Compare with alternative
        </ActionButton>
        <ActionButton
          onClick={handleGenerateADR}
          disabled={!simulationResult || promoting}
          disabledReason={!simulationResult ? 'Run simulation first' : undefined}
        >
          {promoting ? 'Generating…' : 'Generate ADR'}
        </ActionButton>
        <ActionButton
          onClick={handlePromote}
          disabled={!simulationResult || (simulationResult.recommendation?.blocked ?? false) || promoting}
          disabledReason={
            !simulationResult ? 'Run simulation first' :
            simulationResult.recommendation?.blocked ? 'Blocked by veto gate — resolve first' : undefined
          }
        >
          {promoting ? 'Promoting…' : 'Promote to PR'}
        </ActionButton>
        <ActionButton onClick={onDelete} danger disabled={editingBlocked}>
          Remove from architecture
        </ActionButton>
      </div>

      {/* Promotion result */}
      {promotionResult && (
        <div className="mt-3 bg-canvas-bg border border-emerald-500/20 rounded-lg p-3">
          <div className="text-[10px] text-emerald-400 font-semibold mb-1">Artifacts Generated</div>
          <div className="flex flex-col gap-1.5">
            <ArtifactPreview label="isa.yaml patch" content={promotionResult.isa_yaml_patch} />
            <ArtifactPreview label="ADR draft" content={promotionResult.adr_draft} />
            <div className="text-[10px] text-slate-500 mt-1">
              Confidence: {((promotionResult.confidence_check.adjusted_confidence as number) * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {promoError && (
        <div className="mt-2 text-[10px] text-red-400 bg-red-500/10 rounded px-2 py-1">
          {promoError}
        </div>
      )}
    </Section>
  )
}

function ArtifactPreview({ label, content }: { label: string; content: string }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div>
      <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-canvas-accent hover:underline">
        {expanded ? '▾' : '▸'} {label}
      </button>
      {expanded && (
        <pre className="mt-1 text-[9px] font-mono text-slate-500 bg-canvas-surface border border-canvas-border rounded p-2 max-h-32 overflow-auto whitespace-pre-wrap">
          {content}
        </pre>
      )}
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────

function getComponentRole(c: ArchComponent): string | null {
  if (c.type === 'gateway') return 'Entry point · changes may affect all downstream traffic'
  if (c.type === 'data_store' && c.tier === 'tier_1') return 'Core data · changes may affect data integrity & connected services'
  if (c.type === 'data_store') return 'Storage · changes may affect queries & data access patterns'
  if (c.type === 'cache') return 'Performance layer · changes affect latency & DB load'
  if (c.type === 'queue') return 'Async buffer · changes affect event ordering & delivery'
  if (c.type === 'external_system') return 'External dependency · no direct control, SLA-dependent'
  if (c.tier === 'tier_1') return 'Core service · changes may affect critical business flows'
  if (c.tier === 'auxiliary') return 'Support service · low blast radius, safe to modify'
  return null
}

function isStale(isoDate: string): boolean {
  return (Date.now() - new Date(isoDate).getTime()) > 24 * 3600_000
}

function timeAgo(isoDate: string): string {
  const hours = (Date.now() - new Date(isoDate).getTime()) / 3600_000
  if (hours < 1) return `${Math.round(hours * 60)}m ago`
  if (hours < 48) return `${hours.toFixed(0)}h ago`
  return `${(hours / 24).toFixed(0)}d ago`
}
