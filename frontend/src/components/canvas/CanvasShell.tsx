/**
 * CanvasShell — Round 3 polish:
 *   - View Mode labels: "Topology | Cost View | Security View | Blast Radius"
 *   - AI input wider with concrete placeholder
 *   - Run Simulation shows what will be simulated
 *   - Sandbox editing indicator
 *   - Palette collapsible to icon strip
 */

import { useState, useCallback, useEffect } from 'react'
import { useCanvasStore } from '@/store/canvasStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { ComponentPalette } from './ComponentPalette'
import { C4GraphRenderer } from './C4GraphRenderer'
import { ImportYamlModal } from './ImportYamlModal'
import { CommandPalette } from './CommandPalette'
import { AIChatPanel } from '@/components/ai/AIChatPanel'
import { DecisionPanel } from '@/components/panels/DecisionPanel'
import { DesignInspectorPanel } from '@/components/panels/DesignInspectorPanel'
import { SimulationInsights } from '@/components/panels/SimulationInsights'
import { SandboxLayerManager } from '@/components/sandbox/SandboxLayerManager'
import { CommentsLayer } from '@/components/collaboration/CommentsLayer'
import { ComparePanel } from '@/components/panels/ComparePanel'
import { layerApi } from '@/api/endpoints'
import { useSimulation } from '@/hooks/useSimulation'
import clsx from 'clsx'

export type ViewMode = 'topology' | 'cost' | 'security' | 'blast'

const VIEW_MODE_LABELS: Record<ViewMode, string> = {
  topology: 'Topology',
  cost:     'Cost View',
  security: 'Security View',
  blast:    'Blast Radius',
}

const VIEW_MODE_DESCRIPTIONS: Record<ViewMode, string> = {
  topology: 'Structural view — shows components and their dependencies',
  cost:     'Shows estimated monthly cost per component. Identify expensive services and optimize spend.',
  security: 'Highlights risk levels: external-facing, PII, trust boundary crossings.',
  blast:    'Shows which components are affected if a selected service changes. Higher tier = bigger impact.',
}

interface Props {
  editingBlocked: boolean
}

export function CanvasShell({ editingBlocked }: Props) {
  const { isPaletteOpen, togglePalette, activeLayerId, setActiveLayer, selectedNodeIds } = useCanvasStore()
  const { baselineRef, layers, upsertLayer, comparedLayerIds } = useSandboxStore()
  const { startSimulation, activeJob } = useSimulation()

  const [importOpen, setImportOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [rightPanel, setRightPanel] = useState<'decision' | 'inspector' | 'compare' | 'comments'>('decision')
  const [viewMode, setViewMode] = useState<ViewMode>('topology')

  const hasResults = activeJob?.status === 'completed' && activeJob.result !== null
  const layerList = Object.values(layers)
  const selectedId = selectedNodeIds[0] ?? null

  // Auto-switch to Inspector when a node is selected
  useEffect(() => {
    if (selectedId && rightPanel !== 'inspector') {
      setRightPanel('inspector')
    }
  }, [selectedId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Resolve selected component name
  const selectedComponent = (() => {
    if (!activeLayerId || !selectedId) return null
    const ld = layers[activeLayerId]
    return ld?.components.find((c) => c.id === selectedId) ?? null
  })()

  // ── Ctrl+K ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setChatOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', handler)

    // Listen for panel switch events from child components
    const panelHandler = (e: Event) => {
      const panel = (e as CustomEvent).detail
      if (panel) setRightPanel(panel)
    }
    window.addEventListener('archtwin:switch-panel', panelHandler)

    return () => {
      window.removeEventListener('keydown', handler)
      window.removeEventListener('archtwin:switch-panel', panelHandler)
    }
  }, [])

  // ── Run Simulation ─────────────────────────────────────────────────────
  const handleRunSimulation = useCallback(async () => {
    if (!baselineRef) return
    const layersToSim = comparedLayerIds.length > 0
      ? comparedLayerIds
      : activeLayerId ? [activeLayerId] : []
    if (layersToSim.length === 0) return

    // Collect components and relations from all layers being simulated
    const allComponents: Array<Record<string, unknown>> = []
    const allRelations: Array<Record<string, unknown>> = []
    for (const lid of layersToSim) {
      const ld = layers[lid]
      if (ld) {
        allComponents.push(...ld.components.map((c) => ({ ...c })))
        allRelations.push(...ld.relations.map((r) => ({ ...r })))
      }
    }

    await startSimulation({
      baseline_ref: baselineRef,
      proposal_refs: layersToSim,
      optimization_goal: 'balanced',
      reviewers: ['cost', 'performance', 'security'],
      include_blast_radius: true,
      include_calibration: true,
      components: allComponents,
      relations: allRelations,
    })
  }, [baselineRef, comparedLayerIds, activeLayerId, layers, startSimulation])

  const handleAddLayer = useCallback(async () => {
    if (!baselineRef) return
    const title = `Layer ${String.fromCharCode(65 + layerList.length)}`
    try {
      const layer = await layerApi.create({ title, baseline_ref: baselineRef, optimization_goal: 'balanced' })
      upsertLayer(layer)
      setActiveLayer(layer.id)
    } catch { /* silent */ }
  }, [baselineRef, layerList.length, upsertLayer, setActiveLayer])

  const isSimRunning = activeJob?.status === 'running' || activeJob?.status === 'pending'

  // Smart status
  const statusText = (() => {
    if (isSimRunning) return { text: 'Simulation running…', color: 'text-amber-400', dot: 'bg-amber-400 animate-pulse' }
    if (hasResults && activeJob?.result) {
      const conf = activeJob.result.fidelity.adjusted_confidence
      const mode = activeJob.result.fidelity.mode
      if (mode === 'decision_grade') return { text: `Decision-grade · ${(conf*100).toFixed(0)}% confidence`, color: 'text-emerald-400', dot: 'bg-emerald-400' }
      return { text: `Exploratory · ${(conf*100).toFixed(0)}% confidence`, color: 'text-amber-400', dot: 'bg-amber-400' }
    }
    if (selectedComponent) return { text: `${selectedComponent.name} · ready for simulation`, color: 'text-slate-400', dot: 'bg-blue-400' }
    const nodeCount = layerList.find(l => l.proposal.id === activeLayerId)?.components.length ?? 0
    if (activeLayerId && nodeCount > 0) return { text: `${nodeCount} components · Ready`, color: 'text-slate-500', dot: 'bg-slate-500' }
    return { text: 'No layer active', color: 'text-slate-600', dot: 'bg-slate-700' }
  })()

  // Smart CTA label (#4 from review — changes based on state)
  const isBlocked = hasResults && activeJob?.result?.recommendation?.blocked
  const simButtonLabel = isSimRunning
    ? 'Simulating…'
    : isBlocked
    ? 'Resolve Blocker'
    : selectedComponent
    ? `Simulate ${selectedComponent.name}`
    : 'Run Simulation'

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* ═══ Top bar ═══ */}
      <header className="h-11 shrink-0 bg-canvas-surface border-b border-canvas-border flex items-center px-3 gap-2">
        {/* Logo + palette + import */}
        <span className="text-canvas-accent font-bold font-mono text-sm">ArchTwin</span>

        <button
          onClick={togglePalette}
          className={clsx(
            'text-[11px] px-2 py-1 rounded transition-colors',
            isPaletteOpen ? 'text-canvas-accent bg-canvas-accent/10' : 'text-slate-500 hover:text-slate-300',
          )}
        >
          {isPaletteOpen ? '◂ Palette' : '▸ Palette'}
        </button>

        <button onClick={() => setImportOpen(true)} className="text-[11px] text-slate-500 hover:text-slate-300">Import</button>

        <div className="w-px h-5 bg-canvas-border mx-0.5" />

        {/* View Mode switcher — expanded labels */}
        <div className="flex items-center gap-px bg-canvas-bg rounded-lg border border-canvas-border p-0.5">
          {(Object.entries(VIEW_MODE_LABELS) as [ViewMode, string][]).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              title={VIEW_MODE_DESCRIPTIONS[mode]}
              className={clsx(
                'text-[10px] px-2.5 py-1 rounded-md transition-all whitespace-nowrap',
                viewMode === mode
                  ? 'text-canvas-accent bg-canvas-accent/15 font-semibold shadow-sm'
                  : 'text-slate-600 hover:text-slate-400',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Centre: AI command input — wider, concrete placeholder */}
        <div className="flex-1 flex justify-center mx-2">
          <button
            onClick={() => setChatOpen(true)}
            className="flex items-center gap-2 bg-canvas-bg border border-canvas-border rounded-lg px-4 py-1.5 w-full max-w-md hover:border-slate-500 transition-colors group"
          >
            <span className="text-canvas-accent/50 text-sm group-hover:text-canvas-accent/70">✦</span>
            <span className="text-[11px] text-slate-600 group-hover:text-slate-400 flex-1 text-left truncate">
              Ask ArchTwin: compare, optimize cost, explain risk…
            </span>
            <kbd className="text-[9px] text-slate-700 border border-canvas-border rounded px-1.5 py-0.5 shrink-0">⌘K</kbd>
          </button>
        </div>

        {/* Status indicator */}
        <div className={clsx('flex items-center gap-1.5 text-[10px] font-mono shrink-0 mr-2', statusText.color)}>
          <span className={clsx('w-1.5 h-1.5 rounded-full', statusText.dot)} />
          <span className="max-w-[160px] truncate">{statusText.text}</span>
        </div>

        {/* Primary CTA — shows what will be simulated */}
        <button
          onClick={isBlocked ? () => setRightPanel('decision') : handleRunSimulation}
          disabled={editingBlocked || isSimRunning || !activeLayerId}
          className={clsx(
            'text-xs px-4 py-1.5 rounded-lg font-semibold transition-all shrink-0',
            editingBlocked || !activeLayerId
              ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
              : isSimRunning
              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse'
              : isBlocked
              ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
              : 'bg-canvas-accent text-white hover:bg-canvas-accent/80 shadow-lg shadow-canvas-accent/20',
          )}
        >
          {simButtonLabel}
        </button>
      </header>

      {/* ═══ Sandbox editing indicator + layer bar ═══ */}
      <SandboxLayerManager />

      {/* ═══ Main area ═══ */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: palette (collapsible) */}
        <ComponentPalette isOpen={isPaletteOpen} editingBlocked={editingBlocked} />

        {/* Centre: Canvas */}
        <div className="flex-1 relative overflow-hidden">
          {activeLayerId ? (
            <C4GraphRenderer key={activeLayerId} layerId={activeLayerId} editingBlocked={editingBlocked} viewMode={viewMode} />
          ) : (
            <EmptyState onCreateLayer={handleAddLayer} onImport={() => setImportOpen(true)} />
          )}

          {/* Floating simulation insights */}
          {hasResults && activeJob?.result && (
            <SimulationInsights result={activeJob.result} />
          )}

          {/* View mode active badge */}
          {viewMode !== 'topology' && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 bg-canvas-surface/90 backdrop-blur border border-canvas-accent/30 rounded-xl px-4 py-2 flex flex-col items-center gap-0.5">
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-canvas-accent" />
                <span className="text-[11px] text-canvas-accent font-medium">{VIEW_MODE_LABELS[viewMode]} Active</span>
                <button onClick={() => setViewMode('topology')} className="text-[10px] text-slate-500 hover:text-slate-300 ml-1">✕</button>
              </div>
              <span className="text-[10px] text-slate-500 max-w-[300px] text-center">{VIEW_MODE_DESCRIPTIONS[viewMode]}</span>
            </div>
          )}
        </div>

        {/* Right: Decision / Comments */}
        <aside className="w-80 shrink-0 bg-canvas-surface border-l border-canvas-border flex flex-col overflow-hidden transition-all duration-200">
          <div className="flex items-center border-b border-canvas-border shrink-0">
            <button
              onClick={() => setRightPanel('decision')}
              className={clsx(
                'flex-1 text-[11px] py-2 text-center transition-colors',
                rightPanel === 'decision' ? 'text-canvas-accent border-b-2 border-canvas-accent' : 'text-slate-500 hover:text-slate-300',
              )}
            >
              Decision
            </button>
            <button
              onClick={() => setRightPanel('inspector')}
              className={clsx(
                'flex-1 text-[11px] py-2 text-center transition-colors',
                rightPanel === 'inspector' ? 'text-canvas-accent border-b-2 border-canvas-accent' : 'text-slate-500 hover:text-slate-300',
              )}
            >
              Inspector
            </button>
            <button
              onClick={() => setRightPanel('compare')}
              className={clsx(
                'flex-1 text-[11px] py-2 text-center transition-colors',
                rightPanel === 'compare' ? 'text-canvas-accent border-b-2 border-canvas-accent' : 'text-slate-500 hover:text-slate-300',
                comparedLayerIds.length >= 2 && rightPanel !== 'compare' && 'text-purple-400',
              )}
            >
              Compare{comparedLayerIds.length >= 2 ? ` (${comparedLayerIds.length})` : ''}
            </button>
            <button
              onClick={() => setRightPanel('comments')}
              className={clsx(
                'flex-1 text-[11px] py-2 text-center transition-colors',
                rightPanel === 'comments' ? 'text-canvas-accent border-b-2 border-canvas-accent' : 'text-slate-500 hover:text-slate-300',
              )}
            >
              Comments
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {rightPanel === 'decision' && (
              <DecisionPanel
                layerId={activeLayerId}
                editingBlocked={editingBlocked}
                simulationResult={activeJob?.result ?? null}
                onRunSimulation={handleRunSimulation}
              />
            )}
            {rightPanel === 'inspector' && (
              <DesignInspectorPanel
                layerId={activeLayerId}
                editingBlocked={editingBlocked}
              />
            )}
            {rightPanel === 'compare' && (
              <ComparePanel />
            )}
            {rightPanel === 'comments' && activeLayerId && (
              <CommentsLayer layerId={activeLayerId} />
            )}
          </div>
        </aside>
      </div>

      {/* Modals */}
      <ImportYamlModal open={importOpen} onClose={() => setImportOpen(false)} />
      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} />
      <AIChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  )
}

function EmptyState({ onCreateLayer, onImport }: { onCreateLayer: () => void; onImport: () => void }) {
  return (
    <div className="h-full flex items-center justify-center flex-col gap-5 text-slate-500">
      <span className="text-6xl opacity-20">⬡</span>
      <div className="text-center">
        <p className="text-sm text-slate-400 mb-1">Start your architecture design</p>
        <p className="text-[11px] text-slate-600">Import YAML or drag components from the palette</p>
      </div>
      <div className="flex gap-3">
        <button onClick={onImport} className="text-xs px-4 py-2 rounded-lg bg-canvas-accent text-white hover:bg-canvas-accent/80">Import YAML</button>
        <button onClick={onCreateLayer} className="text-xs px-4 py-2 rounded-lg border border-canvas-border text-slate-300 hover:border-slate-500">New Blank Layer</button>
      </div>
    </div>
  )
}
