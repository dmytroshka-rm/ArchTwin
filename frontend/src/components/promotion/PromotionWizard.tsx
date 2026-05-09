/**
 * PromotionWizard — Section 5.4 / 11 DoD item 8.
 * Requests backend-authored isa.yaml patch + ADR draft + persona actions.
 * Canvas NEVER silently mutates production architecture.
 * Promotion is blocked when: security/compliance vetoes, adjusted_confidence < 0.65,
 * or data > 7 days (exploratory only).
 */

import { useState, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { layerApi } from '@/api/endpoints'
import type { PromotionArtifacts } from '@/generated/simulation-result.types'
import type { SimulationResult } from '@/generated/simulation-result.types'
import type { DesignProposal } from '@/generated/isa.types'

interface Props {
  layer: DesignProposal
  simulationResult: SimulationResult | null
  onClose: () => void
}

type Step = 'preflight' | 'artifacts' | 'review' | 'done'

export function PromotionWizard({ layer, simulationResult, onClose }: Props) {
  const [step, setStep]         = useState<Step>('preflight')
  const [artifacts, setArtifacts] = useState<PromotionArtifacts | null>(null)

  // Preflight checks
  const vetoFail = simulationResult
    ? Object.values(simulationResult.veto_gates).some((v) => v === 'fail')
    : false
  const confidence    = simulationResult?.fidelity.adjusted_confidence ?? 1
  const confidenceLow = confidence < 0.65
  const isExploratory = simulationResult?.fidelity.mode === 'exploratory_estimate'
  const isBlocked     = vetoFail || confidenceLow || isExploratory

  const promoteMutation = useMutation({
    mutationFn: () => layerApi.promote(layer.id),
    onSuccess: (data) => {
      setArtifacts(data)
      setStep('artifacts')
    },
  })

  const handleRequestArtifacts = useCallback(() => {
    if (isBlocked) return
    promoteMutation.mutate()
  }, [isBlocked, promoteMutation])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-canvas-surface border border-canvas-border rounded-xl w-[640px] max-h-[85vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-canvas-border">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Promote to PR</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">{layer.title}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">×</button>
        </div>

        {/* Step indicator */}
        <StepIndicator current={step} />

        {/* Content */}
        <div className="p-4">
          {step === 'preflight' && (
            <PreflightStep
              vetoFail={vetoFail}
              confidenceLow={confidenceLow}
              isExploratory={isExploratory}
              confidence={confidence}
              layer={layer}
              isLoading={promoteMutation.isPending}
              onProceed={handleRequestArtifacts}
            />
          )}

          {step === 'artifacts' && artifacts && (
            <ArtifactsStep
              artifacts={artifacts}
              onConfirm={() => setStep('review')}
            />
          )}

          {step === 'review' && artifacts && (
            <ReviewStep
              artifacts={artifacts}
              layer={layer}
              onConfirm={() => setStep('done')}
            />
          )}

          {step === 'done' && (
            <DoneStep layerTitle={layer.title} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Steps ──────────────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: Step }) {
  const steps: Step[] = ['preflight', 'artifacts', 'review', 'done']
  const labels = { preflight: 'Preflight', artifacts: 'Artifacts', review: 'Review', done: 'Done' }
  const idx = steps.indexOf(current)
  return (
    <div className="flex items-center gap-0 px-4 py-2 border-b border-canvas-border">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center">
          <div className={clsx(
            'text-[10px] px-2 py-0.5 rounded font-mono',
            i < idx  ? 'text-status-pass' :
            i === idx ? 'text-canvas-accent font-semibold' :
            'text-slate-600',
          )}>
            {labels[s]}
          </div>
          {i < steps.length - 1 && <span className="text-slate-700 mx-1">›</span>}
        </div>
      ))}
    </div>
  )
}

function PreflightStep({
  vetoFail, confidenceLow, isExploratory, confidence, isLoading, onProceed,
}: {
  vetoFail: boolean; confidenceLow: boolean; isExploratory: boolean
  confidence: number; layer?: DesignProposal; isLoading: boolean; onProceed: () => void
}) {
  const checks = [
    { label: 'Security / Compliance veto',   pass: !vetoFail,     failMsg: 'Proposal is blocked by a security or compliance veto.' },
    { label: `Adjusted confidence ≥ 65%`,    pass: !confidenceLow, failMsg: `Confidence is ${(confidence * 100).toFixed(0)}% — below 65% threshold.` },
    { label: 'Data freshness (< 7 days)',     pass: !isExploratory, failMsg: 'Data is stale (>7 days). Refresh before promoting.' },
  ]

  const allPass = checks.every((c) => c.pass)

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">
        Before generating artifacts, the backend verifies confidence, veto gates and data freshness.
        Canvas never promotes directly — a Git PR remains the final path.
      </p>

      {/* Checklist */}
      <div className="flex flex-col gap-1.5">
        {checks.map((c) => (
          <div key={c.label} className={clsx(
            'flex items-start gap-2 rounded-md px-3 py-2 border text-xs',
            c.pass
              ? 'border-status-pass/30 bg-status-pass/5 text-status-pass'
              : 'border-status-fail/30 bg-status-fail/5 text-status-fail',
          )}>
            <span className="shrink-0">{c.pass ? '✓' : '✕'}</span>
            <div>
              <div className="font-medium">{c.label}</div>
              {!c.pass && <div className="text-[10px] mt-0.5 opacity-80">{c.failMsg}</div>}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={onProceed}
        disabled={!allPass || isLoading}
        className={clsx(
          'w-full py-2 rounded-md text-xs font-semibold mt-1',
          allPass && !isLoading
            ? 'bg-canvas-accent text-white hover:bg-canvas-accent/80'
            : 'bg-canvas-border/50 text-slate-600 cursor-not-allowed',
        )}
      >
        {isLoading ? 'Requesting artifacts…' : 'Request Backend Artifacts'}
      </button>
    </div>
  )
}

function ArtifactsStep({ artifacts, onConfirm }: { artifacts: PromotionArtifacts; onConfirm: () => void }) {
  const [tab, setTab] = useState<'yaml' | 'adr'>('yaml')
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">
        Backend-generated artifacts. Review before proceeding — these will be included in the PR.
      </p>

      <div className="flex gap-1">
        {(['yaml', 'adr'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={clsx(
            'text-xs px-2.5 py-1 rounded border',
            tab === t ? 'border-canvas-accent text-canvas-accent' : 'border-canvas-border text-slate-400',
          )}>
            {t === 'yaml' ? 'isa.yaml patch' : 'ADR draft'}
          </button>
        ))}
      </div>

      <pre className="bg-canvas-bg border border-canvas-border rounded-lg p-3 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-56 overflow-y-auto whitespace-pre-wrap">
        {tab === 'yaml' ? artifacts.isa_yaml_patch : artifacts.adr_draft}
      </pre>

      <button
        onClick={onConfirm}
        className="w-full py-2 rounded-md text-xs font-semibold bg-canvas-accent text-white hover:bg-canvas-accent/80"
      >
        Looks good — continue to review
      </button>
    </div>
  )
}

function ReviewStep({
  artifacts, onConfirm,
}: {
  artifacts: PromotionArtifacts; layer?: DesignProposal; onConfirm: () => void
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">
        Final review before opening a PR. The PR will be opened in your Git repository.
        Canvas does not merge — it only prepares the artifacts.
      </p>

      <div className="bg-canvas-bg border border-canvas-border rounded-lg p-3">
        <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-widest">PR Description</div>
        <p className="text-xs text-slate-300 whitespace-pre-wrap">{artifacts.pr_description}</p>
      </div>

      <div className="text-[11px] text-slate-500">
        Confidence:{' '}
        <span className={artifacts.confidence_check.adjusted_confidence >= 0.8 ? 'text-fidelity-decision' : 'text-fidelity-exploratory'}>
          {(artifacts.confidence_check.adjusted_confidence * 100).toFixed(0)}%
        </span>
      </div>

      <button
        onClick={onConfirm}
        className="w-full py-2 rounded-md text-xs font-semibold bg-status-pass text-white hover:bg-status-pass/80"
      >
        Confirm — Open PR
      </button>
    </div>
  )
}

function DoneStep({ layerTitle, onClose }: { layerTitle: string; onClose: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-4">
      <span className="text-4xl">✓</span>
      <p className="text-sm text-status-pass font-semibold">Artifacts generated</p>
      <p className="text-xs text-slate-400 text-center">
        <strong className="text-slate-300">{layerTitle}</strong> artifacts are ready.<br />
        Open the PR in your Git host to complete the promotion.
      </p>
      <button onClick={onClose} className="mt-2 text-xs px-4 py-2 rounded border border-canvas-border text-slate-400 hover:border-slate-500">
        Close
      </button>
    </div>
  )
}
