/**
 * CommandPalette — Ctrl+K. Now wired to backend /api/ai/command.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { aiApi, type AICommandResult } from '@/api/endpoints'

interface Props {
  open: boolean
  onClose: () => void
}

export function CommandPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AICommandResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus input on open
  useEffect(() => {
    if (open) {
      setQuery('')
      setResult(null)
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Escape to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleSubmit = useCallback(async () => {
    if (!query.trim() || loading) return
    setLoading(true)
    setResult(null)
    try {
      const res = await aiApi.command(query.trim())
      setResult(res)
    } catch {
      setResult({ action: 'error', type: 'error', message: 'Failed to process command. Check backend connection.' })
    } finally {
      setLoading(false)
    }
  }, [query, loading])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]" onClick={onClose}>
      <div className="w-[560px] bg-canvas-surface border border-canvas-border rounded-xl shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Input */}
        <div className="flex items-center px-4 border-b border-canvas-border">
          <span className="text-canvas-accent text-sm mr-2">✦</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setResult(null) }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit() }}
            placeholder="Compare Orders DB with Aurora, optimize cost, explain risk…"
            className="flex-1 bg-transparent text-sm text-slate-200 py-3 outline-none placeholder:text-slate-600"
          />
          {loading ? (
            <span className="text-[10px] text-canvas-accent animate-pulse">thinking…</span>
          ) : (
            <kbd className="text-[10px] text-slate-600 border border-canvas-border rounded px-1.5 py-0.5">↵ send</kbd>
          )}
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto">
          {!result && !loading && (
            <div className="px-4 py-3">
              <div className="text-[10px] text-slate-600 mb-2 uppercase tracking-wider">Try asking:</div>
              {[
                'Compare Orders DB with Aurora Serverless',
                'Optimize this architecture for cost',
                'Show security risks',
                'What is the blast radius of Orders API?',
                'Why is the simulation blocked?',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => { setQuery(suggestion); }}
                  className="w-full text-left text-[11px] text-slate-400 hover:text-canvas-accent hover:bg-canvas-accent/5 px-3 py-1.5 rounded transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          {result && (
            <div className="p-4">
              {/* Message */}
              <div className="text-xs text-slate-200 font-medium mb-2">{result.message}</div>

              {/* Structured result */}
              {result.result && (
                <AIResultView data={result.result} type={result.type} />
              )}

              {/* Suggestions */}
              {result.suggestions && (
                <div className="mt-3 border-t border-canvas-border pt-2">
                  <div className="text-[10px] text-slate-600 mb-1">Follow-up:</div>
                  {result.suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => { setQuery(s); setResult(null) }}
                      className="block text-[11px] text-slate-400 hover:text-canvas-accent py-0.5"
                    >
                      → {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-canvas-border flex items-center justify-between">
          <span className="text-[9px] text-slate-700">Powered by ArchTwin AI Pipeline</span>
          <button onClick={onClose} className="text-[10px] text-slate-600 hover:text-slate-400">Close</button>
        </div>
      </div>
    </div>
  )
}

// ── AI Result renderer ────────────────────────────────────────────────────

function AIResultView({ data, type }: { data: Record<string, unknown>; type: string }) {
  if (type === 'analysis' && 'alternatives' in data) {
    // Comparison result
    const current = data.current as Record<string, string>
    const alts = data.alternatives as Array<Record<string, string>>
    return (
      <div className="space-y-2">
        <div className="bg-canvas-bg rounded-lg p-2.5 border border-canvas-border">
          <div className="text-[10px] text-slate-500 mb-1">Current</div>
          {Object.entries(current).map(([k, v]) => (
            <div key={k} className="flex justify-between text-[11px]">
              <span className="text-slate-500 capitalize">{k.replace('_', ' ')}</span>
              <span className="text-slate-300 font-mono">{v}</span>
            </div>
          ))}
        </div>
        {alts.map((alt, i) => (
          <div key={i} className="bg-canvas-bg rounded-lg p-2.5 border border-purple-500/20">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-purple-400 font-medium">{alt.name}</span>
              <span className="text-[10px] font-mono text-emerald-400">{alt.cost_delta}</span>
            </div>
            {alt.tradeoffs && <div className="text-[10px] text-slate-500">{alt.tradeoffs}</div>}
            {alt.recommendation && <div className="text-[10px] text-canvas-accent mt-1">{alt.recommendation}</div>}
          </div>
        ))}
      </div>
    )
  }

  if (type === 'analysis' && 'optimization_opportunities' in data) {
    // Cost analysis
    const opps = data.optimization_opportunities as Array<Record<string, string>>
    return (
      <div className="space-y-1.5">
        <div className="text-[11px] text-emerald-400 font-mono mb-1">
          Potential saving: {data.total_potential_saving as string}
        </div>
        {opps.map((opp, i) => (
          <div key={i} className="flex items-center gap-2 text-[11px] bg-canvas-bg rounded px-2 py-1.5 border border-canvas-border">
            <span className="text-emerald-400 font-mono shrink-0">{opp.saving}</span>
            <span className="text-slate-300 flex-1">{opp.component}</span>
            <span className="text-slate-500 text-[10px]">{opp.action}</span>
          </div>
        ))}
      </div>
    )
  }

  if (type === 'analysis' && 'overall_status' in data) {
    // Security analysis
    const high = (data.high as Array<Record<string, string>>) ?? []
    const medium = (data.medium as Array<Record<string, string>>) ?? []
    return (
      <div className="space-y-2">
        <div className="text-[11px] text-emerald-400">{data.overall_status as string}</div>
        {high.length > 0 && (
          <div>
            <div className="text-[9px] text-amber-400 uppercase tracking-wider mb-0.5">High Risk</div>
            {high.map((r, i) => (
              <div key={i} className="text-[10px] text-slate-400 bg-amber-500/5 rounded px-2 py-1 border border-amber-500/20 mb-1">
                <span className="text-slate-300">{r.component}</span> — {r.risk}
              </div>
            ))}
          </div>
        )}
        {medium.length > 0 && (
          <div>
            <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Medium Risk</div>
            {medium.map((r, i) => (
              <div key={i} className="text-[10px] text-slate-500 bg-canvas-bg rounded px-2 py-1 border border-canvas-border mb-1">
                {r.component} — {r.risk}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (type === 'explanation' && 'fix_steps' in data) {
    // Explanation with fix steps
    return (
      <div className="space-y-2">
        <div className="text-[11px] text-slate-300 bg-canvas-bg rounded-lg p-2.5 border border-canvas-border">
          {data.detail as string}
        </div>
        <div>
          <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1">Fix steps</div>
          {(data.fix_steps as string[]).map((step, i) => (
            <div key={i} className="text-[10px] text-slate-400 py-0.5">{step}</div>
          ))}
        </div>
      </div>
    )
  }

  if (type === 'explanation') {
    const decisions = Array.isArray(data.key_decisions) ? data.key_decisions as string[] : []
    return (
      <div className="space-y-2">
        {data.summary ? <div className="text-[11px] text-slate-300">{String(data.summary)}</div> : null}
        {decisions.length > 0 && (
          <div className="mt-1">
            {decisions.map((d, i) => (
              <div key={i} className="text-[10px] text-slate-400 flex gap-1.5 py-0.5">
                <span className="text-canvas-accent">•</span> {d}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Fallback: JSON
  return (
    <pre className="text-[10px] text-slate-500 font-mono bg-canvas-bg rounded p-2 overflow-x-auto max-h-48">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}
