/**
 * SandboxLayerManager — redesigned as what-if tabs with deltas.
 * Shows: baseline info, layer goal, simulation status indicators.
 */

import { useCallback } from 'react'
import clsx from 'clsx'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { useSimulationStore } from '@/store/simulationStore'
import { layerApi } from '@/api/endpoints'

interface Props {
  compact?: boolean
}

export function SandboxLayerManager({ compact = false }: Props) {
  const { activeLayerId, setActiveLayer } = useCanvasStore()
  const { layers, baselineRef, comparedLayerIds, setComparedLayers, upsertLayer } = useSandboxStore()
  const { activeJobId, jobs } = useSimulationStore()

  const layerList = Object.values(layers)
  const activeJob = activeJobId ? jobs[activeJobId] : null
  const hasResults = activeJob?.status === 'completed'

  const handleCreateLayer = useCallback(async () => {
    if (!baselineRef) return
    const title = `Layer ${String.fromCharCode(65 + layerList.length)}`
    try {
      const layer = await layerApi.create({ title, baseline_ref: baselineRef, optimization_goal: 'balanced' })
      upsertLayer(layer)
      setActiveLayer(layer.id)
    } catch { /* silent */ }
  }, [baselineRef, layerList.length, upsertLayer, setActiveLayer])

  const toggleCompare = useCallback(
    (layerId: string) => {
      const next = comparedLayerIds.includes(layerId)
        ? comparedLayerIds.filter((id) => id !== layerId)
        : [...comparedLayerIds, layerId]
      setComparedLayers(next)
    },
    [comparedLayerIds, setComparedLayers],
  )

  if (compact || layerList.length === 0) return null

  // Determine if we're editing a sandbox (not baseline)
  const isEditingSandbox = layerList.length > 0

  return (
    <div className="shrink-0 bg-canvas-bg border-b border-canvas-border px-4 py-1.5 flex items-center gap-2 overflow-x-auto">
      {/* Baseline label + sandbox indicator */}
      <div className="flex items-center gap-1.5 mr-2 shrink-0">
        <span className="text-[9px] uppercase tracking-widest text-slate-600">Baseline</span>
        <span className="text-[10px] font-mono text-slate-500 max-w-[100px] truncate" title={baselineRef ?? ''}>
          {baselineRef?.split('@')[0] ?? 'none'}
        </span>
        {isEditingSandbox && (
          <span className="text-[9px] bg-purple-500/15 text-purple-400 border border-purple-500/30 rounded px-1.5 py-0.5 ml-1">
            Sandbox mode · baseline locked · changes generate patch
          </span>
        )}
      </div>

      <div className="w-px h-5 bg-canvas-border shrink-0" />

      {/* Layer tabs */}
      {layerList.map((ld) => {
        const layer = ld.proposal
        const isActive = activeLayerId === layer.id
        const isCompared = comparedLayerIds.includes(layer.id)
        const componentCount = ld.components.length

        // Get score from latest simulation if available
        const score = hasResults && activeJob?.result
          ? activeJob.result.trade_off_matrix.find((r) => r.proposal_id === layer.id)?.recommendation_score
          : undefined

        return (
          <div
            key={layer.id}
            className={clsx(
              'flex items-center gap-2 rounded-lg border px-2.5 py-1 shrink-0 transition-all cursor-pointer group',
              isActive
                ? 'border-blue-500/50 bg-blue-500/10'
                : isCompared
                ? 'border-purple-500/40 bg-purple-500/5'
                : 'border-canvas-border hover:border-slate-600',
            )}
            onClick={() => setActiveLayer(layer.id)}
          >
            {/* Layer name + goal */}
            <div className="min-w-0">
              <div className={clsx('text-[11px] font-medium truncate', isActive ? 'text-blue-400' : 'text-slate-300')}>
                {layer.title}
              </div>
              <div className="text-[9px] text-slate-600 font-mono">
                {layer.optimization_goal.replace('_', '-')} · {componentCount} nodes
              </div>
            </div>

            {/* Score badge (if simulation ran) — labeled (#10) */}
            {score !== undefined && (
              <span className={clsx(
                'text-[9px] font-mono px-1.5 py-0.5 rounded shrink-0',
                score >= 0.7 ? 'bg-emerald-500/15 text-emerald-400' :
                score >= 0.4 ? 'bg-amber-500/15 text-amber-400' :
                'bg-red-500/15 text-red-400',
              )}>
                {score === 0 ? 'Blocked' : `Score ${score.toFixed(2)}`}
              </span>
            )}

            {/* Compare toggle (on hover) */}
            <button
              onClick={(e) => { e.stopPropagation(); toggleCompare(layer.id) }}
              className={clsx(
                'text-[10px] px-1 rounded shrink-0 transition-opacity',
                isCompared ? 'text-purple-400 opacity-100' : 'text-slate-600 opacity-0 group-hover:opacity-100',
              )}
              title={isCompared ? 'Remove from comparison' : 'Add to comparison'}
            >
              {isCompared ? '✓' : '⇄'}
            </button>
          </div>
        )
      })}

      {/* Add layer */}
      <button
        onClick={handleCreateLayer}
        className="shrink-0 text-[11px] px-2.5 py-1.5 rounded-lg border border-dashed border-canvas-border text-slate-600 hover:border-blue-500/50 hover:text-blue-400 transition-colors"
      >
        + What-if
      </button>

      {/* Comparison mode indicator */}
      {comparedLayerIds.length >= 2 && (
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
          <span className="text-[10px] text-purple-400 font-medium">
            Comparing {comparedLayerIds.length}
          </span>
        </div>
      )}
    </div>
  )
}
