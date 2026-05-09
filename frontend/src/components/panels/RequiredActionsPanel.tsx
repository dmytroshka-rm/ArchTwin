/**
 * RequiredActionsPanel — Section 11 / backend Decision-Grade Output Contract.
 * Shows persona-based required actions: developer, architect, security_ops.
 * Actions come exclusively from the backend; no frontend logic derives these.
 */

import { useState } from 'react'
import clsx from 'clsx'
import type { RequiredActions } from '@/generated/simulation-result.types'

interface Props {
  actions: RequiredActions
}

const PERSONAS = [
  { key: 'developer',    label: 'Developer',    icon: '⌨', color: 'text-canvas-accent' },
  { key: 'architect',    label: 'Architect',    icon: '📐', color: 'text-status-info' },
  { key: 'security_ops', label: 'Security/Ops', icon: '🔐', color: 'text-status-warn' },
] as const

type PersonaKey = 'developer' | 'architect' | 'security_ops'

export function RequiredActionsPanel({ actions }: Props) {
  const [checked, setChecked] = useState<Set<string>>(new Set())

  const totalCount = PERSONAS.reduce((s, p) => s + (actions[p.key]?.length ?? 0), 0)

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })

  if (totalCount === 0) {
    return (
      <section className="border-b border-canvas-border">
        <PanelHeader title="Required Actions" count={0} />
        <p className="text-[11px] text-slate-500 p-3">No required actions for this proposal.</p>
      </section>
    )
  }

  return (
    <section className="border-b border-canvas-border">
      <PanelHeader title="Required Actions" count={totalCount} done={checked.size} />

      <div className="p-2 flex flex-col gap-2">
        {PERSONAS.map(({ key, label, icon, color }) => {
          const items = actions[key as PersonaKey] ?? []
          if (items.length === 0) return null
          return (
            <div key={key}>
              <div className={clsx('flex items-center gap-1.5 text-[10px] uppercase tracking-widest mb-1', color)}>
                <span>{icon}</span>
                <span className="font-semibold">{label}</span>
                <span className="text-slate-600 ml-auto">{items.length}</span>
              </div>
              <div className="flex flex-col gap-0.5">
                {items.map((action, i) => {
                  const id = `${key}-${i}`
                  const done = checked.has(id)
                  return (
                    <label
                      key={id}
                      className={clsx(
                        'flex items-start gap-2 rounded px-2 py-1.5 cursor-pointer text-xs',
                        'hover:bg-canvas-border/20 transition-colors',
                        done && 'opacity-50',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={done}
                        onChange={() => toggle(id)}
                        className="mt-0.5 accent-canvas-accent shrink-0"
                      />
                      <span className={clsx(done && 'line-through text-slate-600')}>{action}</span>
                    </label>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function PanelHeader({ title, count, done }: { title: string; count: number; done?: number }) {
  return (
    <div className="px-3 py-2 border-b border-canvas-border flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold flex-1">{title}</span>
      {count > 0 && (
        <span className="text-[10px] font-mono text-slate-500">
          {done !== undefined ? `${done}/` : ''}{count}
        </span>
      )}
    </div>
  )
}
