/**
 * Component palette — collapsible. Full mode shows search + descriptions.
 * Collapsed mode shows only icons (saves space for Canvas).
 */

import { useState, type DragEvent } from 'react'
import clsx from 'clsx'
import type { ComponentType } from '@/generated/isa.types'

interface PaletteItem {
  type: ComponentType
  label: string
  short: string
  icon: string
}

const PALETTE_ITEMS: PaletteItem[] = [
  { type: 'gateway',         icon: '◇', label: 'Gateway',    short: 'API gateway, load balancer' },
  { type: 'service',         icon: '◆', label: 'Service',    short: 'App, API, worker' },
  { type: 'data_store',      icon: '⛁', label: 'Data Store', short: 'Database, storage' },
  { type: 'cache',           icon: '⚡', label: 'Cache',      short: 'Redis, Memcached' },
  { type: 'queue',           icon: '⇶', label: 'Queue',      short: 'Async messaging' },
  { type: 'external_system', icon: '☁', label: 'External',   short: 'Third-party' },
  { type: 'system',          icon: '⬡', label: 'System',     short: 'Bounded context' },
  { type: 'container',       icon: '▣', label: 'Container',  short: 'Deploy unit' },
]

interface Props {
  isOpen: boolean
  editingBlocked: boolean
}

export function ComponentPalette({ isOpen, editingBlocked }: Props) {
  const [search, setSearch] = useState('')
  const [collapsed, setCollapsed] = useState(false)

  const onDragStart = (e: DragEvent<HTMLDivElement>, type: ComponentType) => {
    if (editingBlocked) { e.preventDefault(); return }
    e.dataTransfer.setData('application/isa-cad-node-type', type)
    e.dataTransfer.effectAllowed = 'copy'
  }

  const filtered = search
    ? PALETTE_ITEMS.filter((p) =>
        p.label.toLowerCase().includes(search.toLowerCase()) ||
        p.short.toLowerCase().includes(search.toLowerCase())
      )
    : PALETTE_ITEMS

  // Hidden state — render nothing with slide-out transition
  if (!isOpen) {
    return <aside className="w-0 shrink-0 overflow-hidden transition-all duration-200" />
  }

  // ── Collapsed mode: just icons ──────────────────────────────────────────
  if (collapsed) {
    return (
      <aside className="w-10 shrink-0 bg-canvas-surface border-r border-canvas-border flex flex-col items-center py-1 transition-all duration-200 animate-in slide-in-from-left">
        <button
          onClick={() => setCollapsed(false)}
          className="text-[10px] text-slate-600 hover:text-slate-400 mb-1 py-1"
          title="Expand palette"
        >
          ▸
        </button>
        {PALETTE_ITEMS.map((item) => (
          <div
            key={item.type}
            draggable={!editingBlocked}
            onDragStart={(e) => onDragStart(e, item.type)}
            className={clsx(
              'w-8 h-8 flex items-center justify-center rounded text-base',
              editingBlocked ? 'opacity-30 cursor-not-allowed' : 'cursor-grab hover:bg-canvas-border/40 transition-colors',
            )}
            title={`${item.label} — ${item.short}`}
          >
            <span className="text-slate-400">{item.icon}</span>
          </div>
        ))}
      </aside>
    )
  }

  // ── Full mode ───────────────────────────────────────────────────────────
  return (
    <aside className="w-48 shrink-0 bg-canvas-surface border-r border-canvas-border flex flex-col transition-all duration-200">
      {/* Header with collapse button */}
      <div className="flex items-center px-2 pt-2 pb-1 gap-1">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
          className="flex-1 bg-canvas-bg border border-canvas-border rounded px-2 py-1 text-[11px] text-slate-300 outline-none placeholder:text-slate-600 focus:border-slate-500"
        />
        <button
          onClick={() => setCollapsed(true)}
          className="text-[10px] text-slate-600 hover:text-slate-400 px-1 shrink-0"
          title="Collapse to icons"
        >
          ◂
        </button>
      </div>

      {editingBlocked && (
        <div className="mx-2 my-1 text-[9px] text-red-400/80 bg-red-500/10 rounded px-2 py-1">Editing blocked</div>
      )}

      {/* Items */}
      <div className="flex-1 overflow-y-auto px-1.5 pb-2">
        {filtered.map((item) => (
          <div
            key={item.type}
            draggable={!editingBlocked}
            onDragStart={(e) => onDragStart(e, item.type)}
            className={clsx(
              'flex items-center gap-2 rounded-md px-2 py-2 my-0.5',
              editingBlocked ? 'opacity-30 cursor-not-allowed' : 'cursor-grab hover:bg-canvas-border/40 active:bg-canvas-border/60 transition-colors',
            )}
          >
            <span className="text-base text-slate-400 shrink-0 w-5 text-center">{item.icon}</span>
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-slate-300 leading-tight">{item.label}</div>
              <div className="text-[9px] text-slate-600 leading-tight">{item.short}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Relation legend */}
      <div className="px-3 py-2 border-t border-canvas-border">
        <div className="text-[9px] uppercase tracking-widest text-slate-700 mb-1">Relations</div>
        {[
          { color: '#4f6ef7', label: 'Sync',  dash: false },
          { color: '#f59e0b', label: 'Async', dash: true },
          { color: '#22c55e', label: 'Data',  dash: false },
          { color: '#ef4444', label: 'Risk',  dash: false },
        ].map(({ color, label, dash }) => (
          <div key={label} className="flex items-center gap-2 mb-0.5">
            <svg width="18" height="4"><line x1="0" y1="2" x2="18" y2="2" stroke={color} strokeWidth="1.5" strokeDasharray={dash ? '4 2' : 'none'} /></svg>
            <span className="text-[9px] text-slate-600">{label}</span>
          </div>
        ))}
      </div>
    </aside>
  )
}
