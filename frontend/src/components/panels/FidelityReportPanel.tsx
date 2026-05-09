/**
 * FidelityReportPanel — Section 8.3
 * Shows: base_confidence, freshness_score, staleness_penalty, adjusted_confidence,
 *        mode (decision_grade / exploratory_estimate / blocked),
 *        per-source data ages, calibration note / safety buffer.
 *
 * Enforces:
 *   - "Exploratory Estimate" banner when data > 7 days (disables final promotion)
 *   - "Safety Buffer Applied" note when calibration triggered +15% buffer
 */

import clsx from 'clsx'
import type { FidelityReport } from '@/generated/simulation-result.types'

interface Props {
  fidelity: FidelityReport
}

export function FidelityReportPanel({ fidelity }: Props) {
  const isDecisionGrade  = fidelity.mode === 'decision_grade'
  const isExploratory    = fidelity.mode === 'exploratory_estimate'
  const isBlockedMode    = fidelity.mode === 'blocked'

  return (
    <section className="border-b border-canvas-border">
      <PanelHeader title="Fidelity Report" />

      {/* Mode banner */}
      <div className={clsx(
        'mx-3 mt-2 rounded px-2.5 py-1.5 text-[11px] font-semibold',
        isDecisionGrade ? 'bg-fidelity-decision/10 text-fidelity-decision border border-fidelity-decision/30' :
        isExploratory   ? 'bg-fidelity-exploratory/10 text-fidelity-exploratory border border-fidelity-exploratory/30' :
        'bg-fidelity-blocked/10 text-fidelity-blocked border border-fidelity-blocked/30',
      )}>
        {isDecisionGrade ? '✓ Decision-Grade Forecast' :
         isExploratory   ? '⚠ Exploratory Estimate — Final promotion disabled' :
         isBlockedMode   ? '✕ Blocked — Refresh required before final decision' :
         '✕ Unknown mode'}
      </div>

      {/* Calibration / safety buffer note */}
      {fidelity.safety_buffer_applied && (
        <div className="mx-3 mt-1.5 bg-status-warn/10 border border-status-warn/30 rounded px-2 py-1 text-[10px] text-status-warn">
          Safety buffer (+15%) applied — historical prediction error exceeded 20% threshold.
          {fidelity.calibration_note && <span className="block mt-0.5 opacity-80">{fidelity.calibration_note}</span>}
        </div>
      )}

      <div className="p-3 flex flex-col gap-1.5">
        {/* Confidence breakdown */}
        <Row label="Base Confidence"     value={pct(fidelity.base_confidence)}     />
        <Row label="Data Freshness"      value={pct(fidelity.freshness_score)}      warn={fidelity.freshness_score < 0.7} />
        <Row label="Staleness Penalty"   value={`-${pct(fidelity.staleness_penalty)}`} warn={fidelity.staleness_penalty > 0.05} />
        <Divider />
        <Row
          label="Adjusted Confidence"
          value={pct(fidelity.adjusted_confidence)}
          bold
          color={
            fidelity.adjusted_confidence >= 0.80 ? 'text-fidelity-decision' :
            fidelity.adjusted_confidence >= 0.65 ? 'text-fidelity-exploratory' :
            'text-fidelity-blocked'
          }
        />

        {/* Confidence bar */}
        <div className="h-1.5 bg-canvas-border rounded-full overflow-hidden mt-0.5">
          <div
            className={clsx(
              'h-full rounded-full transition-all',
              fidelity.adjusted_confidence >= 0.80 ? 'bg-fidelity-decision' :
              fidelity.adjusted_confidence >= 0.65 ? 'bg-fidelity-exploratory' :
              'bg-fidelity-blocked',
            )}
            style={{ width: `${fidelity.adjusted_confidence * 100}%` }}
          />
        </div>

        {/* Per-source data ages */}
        {fidelity.data_ages && (
          <>
            <div className="text-[10px] uppercase tracking-widest text-slate-600 mt-2 mb-0.5">Data Ages</div>
            {fidelity.data_ages.inventory_hours !== undefined && (
              <DataAgeRow source="Inventory" ageHours={fidelity.data_ages.inventory_hours} />
            )}
            {fidelity.data_ages.metrics_hours !== undefined && (
              <DataAgeRow source="Metrics" ageHours={fidelity.data_ages.metrics_hours} />
            )}
            {fidelity.data_ages.pricing_hours !== undefined && (
              <DataAgeRow source="Pricing" ageHours={fidelity.data_ages.pricing_hours} />
            )}
          </>
        )}
      </div>
    </section>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────

function pct(v: number) { return `${(v * 100).toFixed(1)}%` }

function Row({
  label, value, bold, warn, color,
}: {
  label: string; value: string; bold?: boolean; warn?: boolean; color?: string
}) {
  return (
    <div className="flex justify-between items-center text-[11px]">
      <span className="text-slate-500">{label}</span>
      <span className={clsx('font-mono', bold && 'font-semibold', warn ? 'text-status-warn' : (color ?? 'text-slate-300'))}>
        {value}
      </span>
    </div>
  )
}

function Divider() {
  return <div className="border-t border-canvas-border/40 my-0.5" />
}

function DataAgeRow({ source, ageHours }: { source: string; ageHours: number }) {
  const isWarn  = ageHours > 24
  const isBlock = ageHours > 168   // 7 days
  return (
    <div className="flex justify-between text-[11px]">
      <span className="text-slate-500">{source}</span>
      <span className={clsx(
        'font-mono',
        isBlock ? 'text-fidelity-blocked' :
        isWarn  ? 'text-fidelity-exploratory' :
        'text-fidelity-decision',
      )}>
        {ageHours < 1
          ? `${Math.round(ageHours * 60)}m`
          : ageHours < 48
          ? `${ageHours.toFixed(1)}h`
          : `${(ageHours / 24).toFixed(1)}d`}
        {isBlock && ' ⚠ >7d'}
      </span>
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
