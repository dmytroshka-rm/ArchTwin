/**
 * TradeoffMatrixPanel — Section 8.2
 * Columns: Cost, Performance, Security, Reliability, Complexity, Fidelity,
 *          Veto Status, Recommendation Score.
 * All values are backend-returned. No frontend scoring.
 * Blocked proposals remain visible but show BLOCKED and cannot be promoted.
 */

import clsx from 'clsx'
import type { SimulationResult } from '@/generated/simulation-result.types'
import type { TradeoffMatrixRow } from '@/generated/simulation-result.types'

interface Props {
  result: SimulationResult
}

const SCORE_COLOR = (v: number) =>
  v >= 0.75 ? 'text-status-pass' :
  v >= 0.50 ? 'text-status-warn' :
  'text-status-fail'

const VETO_COLOR: Record<string, string> = {
  pass: 'text-status-pass',
  fail: 'text-status-fail',
  warn: 'text-status-warn',
}

const COLUMNS = [
  { key: 'cost_score',           label: 'Cost'   },
  { key: 'performance_score',    label: 'Perf'   },
  { key: 'security_score',       label: 'Sec'    },
  { key: 'reliability_score',    label: 'Rel'    },
  { key: 'complexity_score',     label: 'Cmpx'   },
  { key: 'fidelity_score',       label: 'Fid'    },
]

export function TradeoffMatrixPanel({ result }: Props) {
  const { trade_off_matrix: rows, recommendation } = result

  if (!rows || rows.length === 0) {
    return (
      <section className="border-b border-canvas-border">
        <PanelHeader title="Trade-off Matrix" />
        <p className="text-[11px] text-slate-500 p-3">No trade-off data available.</p>
      </section>
    )
  }

  return (
    <section className="border-b border-canvas-border">
      <PanelHeader title="Trade-off Matrix" />

      {/* Recommendation banner */}
      {recommendation && !recommendation.blocked && (
        <div className="mx-3 mt-2 bg-status-pass/10 border border-status-pass/30 rounded px-2 py-1.5">
          <div className="text-[10px] text-status-pass font-semibold uppercase tracking-wide">
            Recommendation — {recommendation.optimization_goal.replace('_', ' ')}
          </div>
          <div className="text-xs text-slate-300 mt-0.5 font-mono">
            {recommendation.winner} · score {recommendation.recommendation_score.toFixed(2)}
          </div>
          {recommendation.rationale && (
            <div className="text-[10px] text-slate-400 mt-0.5">{recommendation.rationale}</div>
          )}
        </div>
      )}

      {/* Veto summary */}
      <VetoSummary gates={result.veto_gates} />

      {/* Matrix table */}
      <div className="overflow-x-auto px-3 pb-3 mt-2">
        <table className="w-full text-[11px] border-collapse">
          <thead>
            <tr>
              <th className="text-left text-slate-500 pb-1 pr-2 font-normal">Layer</th>
              {COLUMNS.map((col) => (
                <th key={col.key} className="text-right text-slate-500 pb-1 px-1 font-normal w-10">
                  {col.label}
                </th>
              ))}
              <th className="text-right text-slate-500 pb-1 px-1 font-normal">Veto</th>
              <th className="text-right text-slate-500 pb-1 pl-1 font-normal">Score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <MatrixRow
                key={row.proposal_id}
                row={row}
                isWinner={recommendation?.winner === row.proposal_id && !recommendation.blocked}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function MatrixRow({ row, isWinner }: { row: TradeoffMatrixRow; isWinner: boolean }) {
  return (
    <tr
      className={clsx(
        'border-t border-canvas-border/40',
        row.blocked ? 'opacity-60' : '',
        isWinner ? 'bg-status-pass/5' : '',
      )}
    >
      <td className="py-1 pr-2">
        <span className={clsx('font-medium text-xs', isWinner ? 'text-status-pass' : 'text-slate-300')}>
          {row.label}
        </span>
        {row.is_baseline && (
          <span className="ml-1 text-[9px] text-slate-500 bg-canvas-border/50 rounded px-1">BL</span>
        )}
        {row.blocked && (
          <span className="ml-1 text-[9px] text-status-blocked bg-status-blocked/10 rounded px-1">BLOCKED</span>
        )}
      </td>

      {COLUMNS.map((col) => {
        const val = row[col.key as keyof TradeoffMatrixRow] as number
        return (
          <td key={col.key} className={clsx('text-right px-1 font-mono', SCORE_COLOR(val))}>
            {val.toFixed(2)}
          </td>
        )
      })}

      <td className={clsx('text-right px-1 font-mono text-[10px]', VETO_COLOR[row.veto_status] ?? 'text-slate-400')}>
        {row.veto_status}
      </td>
      <td className={clsx('text-right pl-1 font-mono font-semibold', SCORE_COLOR(row.recommendation_score))}>
        {row.recommendation_score.toFixed(2)}
      </td>
    </tr>
  )
}

function VetoSummary({ gates }: { gates: SimulationResult['veto_gates'] }) {
  const entries = Object.entries(gates) as [string, string][]
  const anyFail = entries.some(([, v]) => v === 'fail')

  return (
    <div className="flex items-center gap-2 px-3 pt-2 flex-wrap">
      {entries.map(([gate, status]) => (
        <span
          key={gate}
          className={clsx(
            'text-[10px] font-mono px-1.5 py-0.5 rounded border',
            status === 'pass' ? 'border-status-pass/30 text-status-pass' :
            status === 'fail' ? 'border-status-fail/30 text-status-fail bg-status-fail/10' :
            status === 'warn' ? 'border-status-warn/30 text-status-warn' :
            'border-canvas-border text-slate-500',
          )}
        >
          {gate}: {status}
        </span>
      ))}
      {anyFail && (
        <span className="text-[10px] text-status-fail ml-auto">Promotion blocked</span>
      )}
    </div>
  )
}

function PanelHeader({ title }: { title: string }) {
  return (
    <div className="px-3 py-2 border-b border-canvas-border">
      <span className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">{title}</span>
    </div>
  )
}
