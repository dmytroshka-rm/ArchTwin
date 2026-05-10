/**
 * AIChatPanel — full conversational AI assistant panel.
 * Docked to the right, toggled via button. Persists history in localStorage.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { aiApi, type AICanvasAction } from '@/api/endpoints'
import { useLLMSettingsStore } from '@/store/llmSettingsStore'
import { useSandboxStore } from '@/store/sandboxStore'
import { useCanvasStore } from '@/store/canvasStore'
import type { ArchComponent, ArchRelation } from '@/generated/isa.types'
import clsx from 'clsx'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  result?: Record<string, unknown>
  suggestions?: string[]
  canvas_actions?: AICanvasAction[]
  actionsApplied?: boolean
}

const STORAGE_KEY = 'archtwin-ai-chat'

function loadHistory(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveHistory(messages: Message[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-50))) } catch { /* */ }
}

interface Props {
  open: boolean
  onClose: () => void
}

export function AIChatPanel({ open, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>(loadHistory)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  // Focus input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const sendMessage = useCallback(async (text?: string) => {
    const msg = text ?? input.trim()
    if (!msg || loading) return
    setInput('')

    const userMsg: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: msg,
      timestamp: Date.now(),
    }
    const updated = [...messages, userMsg]
    setMessages(updated)
    saveHistory(updated)
    setLoading(true)

    try {
      const { apiKey, provider, selectedModel } = useLLMSettingsStore.getState()
      const llmConfig = apiKey ? { api_key: apiKey, provider, model: selectedModel } : undefined

      // Build architecture context from current Canvas state
      const activeLayerId = useCanvasStore.getState().activeLayerId
      const layer = activeLayerId ? useSandboxStore.getState().getLayer(activeLayerId) : undefined
      const context: Record<string, unknown> = {}
      if (layer) {
        context.components = layer.components.map((c) => ({
          name: c.name, type: c.type, tier: c.tier, technology: c.technology,
        }))
        context.relations = layer.relations.map((r) => ({
          source: r.source_id, target: r.target_id, type: r.type, protocol: r.protocol,
        }))
        context.layer_title = layer.proposal.title
        context.optimization_goal = layer.proposal.optimization_goal
      }

      let result = await aiApi.command(msg, context, llmConfig)

      // If backend returned raw JSON as message (parsing failed), try to extract on frontend
      if (!result.canvas_actions && result.message && result.message.includes('"canvas_actions"')) {
        try {
          let raw = result.message
          // Strip markdown fences
          if (raw.includes('```')) {
            raw = raw.replace(/```json?\n?/g, '').replace(/```/g, '')
          }
          // Fix trailing commas
          raw = raw.replace(/,\s*([}\]])/g, '$1')
          // Fix double quotes
          raw = raw.replace(/""/g, '"')
          const parsed = JSON.parse(raw)
          if (parsed && parsed.message && parsed.canvas_actions) {
            result = parsed
          }
        } catch { /* keep original */ }
      }

      const assistantMsg: Message = {
        id: `msg-${Date.now()}-ai`,
        role: 'assistant',
        content: result.message,
        timestamp: Date.now(),
        result: result.result,
        suggestions: result.suggestions,
        canvas_actions: result.canvas_actions,
      }
      const withResponse = [...updated, assistantMsg]
      setMessages(withResponse)
      saveHistory(withResponse)
    } catch {
      const errMsg: Message = {
        id: `msg-${Date.now()}-err`,
        role: 'assistant',
        content: 'Failed to get response. Check that the backend is running.',
        timestamp: Date.now(),
      }
      const withErr = [...updated, errMsg]
      setMessages(withErr)
      saveHistory(withErr)
    } finally {
      setLoading(false)
    }
  }, [input, messages, loading])

  const applyCanvasActions = useCallback((msgId: string, actions: AICanvasAction[]) => {
    const activeLayerId = useCanvasStore.getState().activeLayerId
    if (!activeLayerId) return

    const store = useSandboxStore.getState()
    const canvasStore = useCanvasStore.getState()
    const layer = store.getLayer(activeLayerId)
    if (!layer) return

    // Track name→id mapping for newly created components (so relations can reference them)
    // Store both exact and lowercase for fuzzy matching
    const nameToId: Record<string, string> = {}
    const addMapping = (name: string, id: string) => {
      nameToId[name.toLowerCase()] = id
      nameToId[name.toLowerCase().replace(/\s+/g, '-')] = id
      nameToId[name.toLowerCase().replace(/\s+/g, '_')] = id
    }
    // Existing components
    for (const c of layer.components) {
      addMapping(c.name, c.id)
    }

    // Helper to find component id by name (tries multiple formats)
    const findId = (name: string): string | undefined => {
      const lower = name.toLowerCase()
      return nameToId[lower] || nameToId[lower.replace(/\s+/g, '-')] || nameToId[lower.replace(/\s+/g, '_')]
    }

    // Count existing nodes for grid layout offset
    const existingCount = layer.components.length
    const COLS = 4
    const GRID_X = 250
    const GRID_Y = 180
    const START_X = 80
    const START_Y = 80
    let addedIndex = 0

    // First pass: add components (so they exist for relations)
    for (const action of actions) {
      if (action.op === 'add_component' && action.name) {
        const id = `component.${(action.type ?? 'service').replace('_', '-')}.${action.name.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}-${addedIndex}`
        const newComp: ArchComponent = {
          id,
          name: action.name,
          type: (action.type ?? 'service') as ArchComponent['type'],
          technology: action.technology,
          tier: (action.tier ?? 'standard') as ArchComponent['tier'],
          ...((action as any).observed_metrics ? { observed_metrics: (action as any).observed_metrics } : {}),
          ...((action as any).data_classification ? { data_classification: (action as any).data_classification } : {}),
        }
        store.upsertComponent(activeLayerId, newComp)
        addMapping(action.name, id)

        // Auto-layout: grid position
        const gridIdx = existingCount + addedIndex
        const col = gridIdx % COLS
        const row = Math.floor(gridIdx / COLS)
        canvasStore.setNodeLayout(id, { x: START_X + col * GRID_X, y: START_Y + row * GRID_Y })
        addedIndex++
      }

      if (action.op === 'remove_component' && action.name) {
        const compId = findId(action.name)
        if (compId) store.removeComponent(activeLayerId, compId)
      }

      if (action.op === 'update_component' && action.name && action.changes) {
        const compId = findId(action.name)
        if (compId) {
          const current = store.getLayer(activeLayerId)?.components.find((c) => c.id === compId)
          if (current) {
            store.upsertComponent(activeLayerId, { ...current, ...action.changes } as ArchComponent)
          }
        }
      }
    }

    // Second pass: add/remove relations (now all components exist)
    for (const action of actions) {
      if (action.op === 'add_relation' && action.source && action.target) {
        const srcId = findId(action.source)
        const tgtId = findId(action.target)
        if (srcId && tgtId) {
          const newRel: ArchRelation = {
            id: `rel-${srcId.slice(-8)}-${tgtId.slice(-8)}-${Date.now()}`,
            source_id: srcId,
            target_id: tgtId,
            type: (action.type ?? 'synchronous') as ArchRelation['type'],
            protocol: action.protocol ?? 'HTTPS',
          }
          store.upsertRelation(activeLayerId, newRel)
        }
      }

      if (action.op === 'remove_relation' && action.source && action.target) {
        const srcId = findId(action.source)
        const tgtId = findId(action.target)
        if (srcId && tgtId) {
          const currentLayer = store.getLayer(activeLayerId)
          const rel = currentLayer?.relations.find((r) => r.source_id === srcId && r.target_id === tgtId)
          if (rel) store.removeRelation(activeLayerId, rel.id)
        }
      }
    }

    // Mark actions as applied
    setMessages((prev) => prev.map((m) => m.id === msgId ? { ...m, actionsApplied: true } : m))
  }, [])

  const clearHistory = useCallback(() => {
    setMessages([])
    localStorage.removeItem(STORAGE_KEY)
  }, [])

  if (!open) return null

  return (
    <div className="fixed right-0 top-0 h-full w-96 bg-canvas-surface border-l border-canvas-border shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="h-12 shrink-0 border-b border-canvas-border flex items-center px-4 gap-2">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-canvas-accent">
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
        <span className="text-sm font-semibold text-slate-200 flex-1">AI Assistant</span>
        <button onClick={clearHistory} className="text-[10px] text-slate-600 hover:text-slate-400 mr-2" title="Clear history">
          Clear
        </button>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <div className="text-2xl mb-2 opacity-50">⬡</div>
            <p className="text-[12px] text-slate-500 mb-4">Ask about your architecture</p>
            <div className="space-y-1.5">
              {['Compare Orders DB alternatives', 'Optimize this layer for cost', 'Show security risks', 'Explain why reliability gate failed'].map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  className="block w-full text-left text-[11px] text-slate-400 bg-canvas-bg/50 border border-canvas-border rounded-lg px-3 py-2 hover:border-canvas-accent/30 hover:text-slate-300 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={clsx(
              'max-w-[85%] rounded-lg px-3 py-2 text-[12px] leading-relaxed',
              msg.role === 'user'
                ? 'bg-canvas-accent/15 text-slate-200'
                : 'bg-canvas-bg border border-canvas-border text-slate-300',
            )}>
              <p className="whitespace-pre-wrap">{msg.content}</p>

              {/* Structured result */}
              {msg.result && (
                <pre className="mt-2 text-[10px] font-mono text-slate-400 bg-canvas-surface/50 rounded p-2 overflow-x-auto max-h-40 overflow-y-auto">
                  {JSON.stringify(msg.result, null, 2)}
                </pre>
              )}

              {/* Suggestions */}
              {/* Canvas actions — AI proposed changes */}
              {msg.canvas_actions && msg.canvas_actions.length > 0 && (
                <div className="mt-2 border border-purple-500/30 bg-purple-500/5 rounded-lg p-2">
                  <div className="text-[9px] text-purple-400 uppercase tracking-wider font-semibold mb-1.5">
                    Proposed changes ({msg.canvas_actions.length})
                  </div>
                  <div className="space-y-1 mb-2">
                    {msg.canvas_actions.map((a, i) => (
                      <div key={i} className="text-[10px] text-slate-400 flex items-center gap-1.5">
                        <span className={clsx(
                          'w-4 text-center font-mono text-[9px]',
                          a.op.startsWith('add') ? 'text-status-pass' :
                          a.op.startsWith('remove') ? 'text-status-fail' : 'text-status-warn',
                        )}>
                          {a.op.startsWith('add') ? '+' : a.op.startsWith('remove') ? '−' : '~'}
                        </span>
                        <span>
                          {a.op === 'add_component' && `Add ${a.type}: "${a.name}" (${a.technology ?? ''})`}
                          {a.op === 'remove_component' && `Remove: "${a.name}"`}
                          {a.op === 'update_component' && `Update "${a.name}": ${JSON.stringify(a.changes)}`}
                          {a.op === 'add_relation' && `Connect: ${a.source} → ${a.target} (${a.protocol ?? a.type})`}
                          {a.op === 'remove_relation' && `Disconnect: ${a.source} → ${a.target}`}
                        </span>
                      </div>
                    ))}
                  </div>
                  {!msg.actionsApplied ? (
                    <button
                      onClick={() => applyCanvasActions(msg.id, msg.canvas_actions!)}
                      className="w-full text-[11px] py-1.5 bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-md hover:bg-purple-500/30 transition-colors font-medium"
                    >
                      Apply changes to Canvas
                    </button>
                  ) : (
                    <div className="text-[10px] text-status-pass text-center py-1">
                      ✓ Applied to Canvas
                    </div>
                  )}
                </div>
              )}

              {msg.suggestions && msg.suggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => sendMessage(s)}
                      className="text-[10px] px-2 py-0.5 rounded bg-canvas-accent/10 text-canvas-accent border border-canvas-accent/20 hover:bg-canvas-accent/20 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Loading */}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-canvas-border p-3">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
            placeholder="Ask about architecture..."
            className="flex-1 bg-canvas-bg border border-canvas-border rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:border-canvas-accent placeholder:text-slate-600"
            disabled={loading}
          />
          <button
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            className="px-3 py-2 bg-canvas-accent text-white rounded-lg hover:bg-canvas-accent/80 disabled:opacity-50 transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <p className="text-[9px] text-slate-600 mt-1.5 text-center">Ctrl+K to toggle • Responses from backend AI pipeline</p>
      </div>
    </div>
  )
}
