/**
 * ImportYamlModal — allows users to paste or upload a YAML architecture file.
 * Sends to backend for parsing, then loads the result into the Canvas.
 */

import { useState, useCallback, useRef } from 'react'
import clsx from 'clsx'
import { api } from '@/api/client'
import { useSandboxStore } from '@/store/sandboxStore'
import { useCanvasStore } from '@/store/canvasStore'
import type { ArchComponent, ArchRelation, DesignProposal } from '@/generated/isa.types'

interface ImportResult {
  layer: DesignProposal
  components: ArchComponent[]
  relations: ArchRelation[]
  positions: Record<string, { x: number; y: number }>
  baseline_ref: string
  warnings: string[]
}

interface Props {
  open: boolean
  onClose: () => void
}

const EXAMPLE_YAML = `name: "My Microservices"
baseline_ref: "baseline.prod@v1"

components:
  - name: "API Gateway"
    type: "gateway"
    technology: "nginx"
    tier: "tier_1"

  - name: "User Service"
    type: "service"
    technology: "node"
    tier: "tier_1"
    metrics:
      p99_latency_ms: 45
      requests_per_second: 5000

  - name: "Users DB"
    type: "data_store"
    technology: "postgresql"
    tier: "tier_1"

  - name: "Cache"
    type: "cache"
    technology: "redis"
    tier: "standard"
    metrics:
      cache_hit_ratio: 0.88

  - name: "Message Queue"
    type: "queue"
    technology: "rabbitmq"
    tier: "standard"

  - name: "Email Service"
    type: "service"
    technology: "python"
    tier: "auxiliary"

relations:
  - source: "API Gateway"
    target: "User Service"
    type: "synchronous"
    protocol: "HTTPS"
    criticality: "high"

  - source: "User Service"
    target: "Users DB"
    type: "data_access"
    protocol: "PostgreSQL"

  - source: "User Service"
    target: "Cache"
    type: "data_access"
    protocol: "Redis"

  - source: "User Service"
    target: "Message Queue"
    type: "asynchronous"
    protocol: "AMQP"

  - source: "Message Queue"
    target: "Email Service"
    type: "asynchronous"
    protocol: "AMQP"
`

export function ImportYamlModal({ open, onClose }: Props) {
  const [yamlContent, setYamlContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [success, setSuccess] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { setBaselineRef, upsertLayer, setLayerComponents, setLayerRelations } = useSandboxStore()
  const { setActiveLayer, setNodeLayout } = useCanvasStore()

  const handleImport = useCallback(async () => {
    if (!yamlContent.trim()) {
      setError('Paste or upload a YAML file first.')
      return
    }

    setLoading(true)
    setError(null)
    setWarnings([])
    setSuccess(false)

    try {
      const data = await api.post<ImportResult>('/import/yaml', { yaml_content: yamlContent })

      // Set state
      setBaselineRef(data.baseline_ref)
      upsertLayer(data.layer)
      setActiveLayer(data.layer.id)
      setLayerComponents(data.layer.id, data.components)
      setLayerRelations(data.layer.id, data.relations)

      // Set positions
      for (const [nodeId, pos] of Object.entries(data.positions)) {
        setNodeLayout(nodeId, { x: pos.x, y: pos.y })
      }

      setWarnings(data.warnings)
      setSuccess(true)

      // Close after short delay
      setTimeout(() => onClose(), 1500)
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'body' in e) {
        const body = (e as { body: unknown }).body
        if (body && typeof body === 'object' && 'detail' in body) {
          setError(String((body as { detail: string }).detail))
        } else {
          setError('Import failed — check YAML syntax.')
        }
      } else {
        setError(`Import failed: ${e instanceof Error ? e.message : 'Unknown error'}`)
      }
    } finally {
      setLoading(false)
    }
  }, [yamlContent, setBaselineRef, upsertLayer, setActiveLayer, setLayerComponents, setLayerRelations, setNodeLayout, onClose])

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result
      if (typeof text === 'string') {
        setYamlContent(text)
        setError(null)
      }
    }
    reader.readAsText(file)
  }, [])

  const loadExample = useCallback(() => {
    setYamlContent(EXAMPLE_YAML)
    setError(null)
  }, [])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-canvas-surface border border-canvas-border rounded-xl w-[700px] max-h-[85vh] overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-canvas-border shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Import Architecture from YAML</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">Paste your architecture YAML or upload a .yaml file</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">×</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3">
          {/* Actions bar */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-xs px-3 py-1.5 rounded border border-canvas-border text-slate-300 hover:border-canvas-accent hover:text-canvas-accent"
            >
              Upload .yaml file
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".yaml,.yml"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={loadExample}
              className="text-xs px-3 py-1.5 rounded border border-canvas-border text-slate-400 hover:border-slate-500 hover:text-slate-300"
            >
              Load Example
            </button>
            <span className="flex-1" />
            <span className="text-[10px] text-slate-600">
              {yamlContent ? `${yamlContent.split('\n').length} lines` : 'empty'}
            </span>
          </div>

          {/* Textarea */}
          <textarea
            value={yamlContent}
            onChange={(e) => { setYamlContent(e.target.value); setError(null) }}
            placeholder="Paste your YAML architecture here..."
            className={clsx(
              'w-full flex-1 min-h-[300px] bg-canvas-bg border rounded-lg px-4 py-3',
              'text-xs font-mono text-slate-200 resize-none outline-none',
              'placeholder:text-slate-600',
              error ? 'border-status-fail/50' : 'border-canvas-border focus:border-canvas-accent',
            )}
            spellCheck={false}
          />

          {/* Error */}
          {error && (
            <div className="bg-status-fail/10 border border-status-fail/30 rounded-lg px-3 py-2 text-[11px] text-status-fail">
              {error}
            </div>
          )}

          {/* Warnings */}
          {warnings.length > 0 && (
            <div className="bg-status-warn/10 border border-status-warn/30 rounded-lg px-3 py-2">
              <div className="text-[10px] text-status-warn font-semibold mb-1">Warnings ({warnings.length})</div>
              {warnings.map((w, i) => (
                <div key={i} className="text-[11px] text-status-warn/80">• {w}</div>
              ))}
            </div>
          )}

          {/* Success */}
          {success && (
            <div className="bg-status-pass/10 border border-status-pass/30 rounded-lg px-3 py-2 text-[11px] text-status-pass font-semibold">
              ✓ Architecture imported successfully! Loading canvas...
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-canvas-border flex items-center gap-3 shrink-0">
          <button
            onClick={onClose}
            className="text-xs px-4 py-2 rounded border border-canvas-border text-slate-400 hover:border-slate-500"
          >
            Cancel
          </button>
          <div className="flex-1" />
          <button
            onClick={handleImport}
            disabled={!yamlContent.trim() || loading || success}
            className={clsx(
              'text-xs px-5 py-2 rounded-lg font-semibold',
              yamlContent.trim() && !loading && !success
                ? 'bg-canvas-accent text-white hover:bg-canvas-accent/80'
                : 'bg-canvas-border/50 text-slate-600 cursor-not-allowed',
            )}
          >
            {loading ? 'Importing...' : success ? 'Done ✓' : 'Import Architecture'}
          </button>
        </div>
      </div>
    </div>
  )
}
