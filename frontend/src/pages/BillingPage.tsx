import { Link } from 'react-router-dom'
import { useEffect, useCallback } from 'react'
import { useBillingStore } from '@/store/billingStore'
import { billingApi } from '@/api/endpoints'

export function BillingPage() {
  const {
    plan, status, currentPeriodEnd, cancelAtPeriodEnd,
    trialEndsAt, entitlements, usage, loaded, loading,
    setSubscription, setLoading, setError,
  } = useBillingStore()

  // Load subscription on mount
  useEffect(() => {
    setLoading(true)
    billingApi.getSubscription().then((info) => {
      setSubscription(info)
    }).catch((err) => {
      setError(String(err))
    })
  }, [setSubscription, setLoading, setError])

  const handleManageBilling = useCallback(async () => {
    try {
      const { portal_url } = await billingApi.openPortal()
      window.location.href = portal_url
    } catch {
      console.error('Failed to open billing portal')
    }
  }, [])

  if (loading || !loaded) {
    return (
      <div className="min-h-screen bg-canvas-bg flex flex-col">
        <Nav />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-sm text-slate-500">Loading billing info...</div>
        </div>
      </div>
    )
  }

  const statusColor = STATUS_COLORS[status] ?? 'text-slate-400'

  return (
    <div className="min-h-screen bg-canvas-bg flex flex-col">
      <Nav />

      <main className="flex-1 max-w-[780px] mx-auto px-6 py-10 w-full">
        <h1 className="text-2xl font-bold text-slate-100 mb-2">Billing & Subscription</h1>
        <p className="text-sm text-slate-500 mb-8">Manage your plan, usage, and payment settings.</p>

        {/* ── Current Plan ────────────────────────────────────────────── */}
        <section className="mb-8">
          <SectionTitle>Current Plan</SectionTitle>
          <div className="bg-canvas-surface/40 border border-canvas-border rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <PlanBadge plan={plan} />
                  <span className={`text-[11px] ${statusColor} capitalize`}>{status}</span>
                </div>
                {currentPeriodEnd && (
                  <div className="text-[11px] text-slate-500 mt-1">
                    {cancelAtPeriodEnd ? 'Access until' : 'Renews'}: {new Date(currentPeriodEnd).toLocaleDateString()}
                  </div>
                )}
                {trialEndsAt && (
                  <div className="text-[11px] text-status-warn mt-1">
                    Trial ends: {new Date(trialEndsAt).toLocaleDateString()}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                {plan !== 'enterprise' && (
                  <Link
                    to="/pricing"
                    className="text-[12px] px-4 py-2 bg-canvas-accent text-white rounded-lg font-medium hover:bg-canvas-accent/80 transition-colors"
                  >
                    {plan === 'free' ? 'Upgrade' : 'Change Plan'}
                  </Link>
                )}
                {plan !== 'free' && (
                  <button
                    onClick={handleManageBilling}
                    className="text-[12px] px-4 py-2 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors"
                  >
                    Manage Billing
                  </button>
                )}
              </div>
            </div>

            {cancelAtPeriodEnd && (
              <div className="flex items-center gap-2 bg-status-warn/5 border border-status-warn/20 rounded-lg px-3 py-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-warn">
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <span className="text-[11px] text-slate-400">
                  Your subscription is set to cancel. You'll be downgraded to Free at the end of the billing period.
                </span>
              </div>
            )}

            {status === 'past_due' && (
              <div className="flex items-center gap-2 bg-status-fail/5 border border-status-fail/20 rounded-lg px-3 py-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-fail">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
                <span className="text-[11px] text-slate-400">
                  Payment failed. Please update your payment method to avoid service interruption.
                </span>
              </div>
            )}
          </div>
        </section>

        {/* ── Usage ───────────────────────────────────────────────────── */}
        <section className="mb-8">
          <SectionTitle>Usage This Period</SectionTitle>
          <div className="bg-canvas-surface/40 border border-canvas-border rounded-xl p-5 space-y-4">
            <UsageRow label="Simulations" counter={usage.simulations_run} />
            <UsageRow label="Projects" counter={usage.projects_created} />
            <UsageRow label="Sandbox Layers" counter={usage.sandbox_layers_created} />
            <UsageRow label="ADR Generated" counter={usage.adr_generated} />
            <UsageRow label="YAML Exports" counter={usage.yaml_exports} />
          </div>
        </section>

        {/* ── Plan Details ────────────────────────────────────────────── */}
        <section className="mb-8">
          <SectionTitle>Plan Entitlements</SectionTitle>
          <div className="bg-canvas-surface/40 border border-canvas-border rounded-xl p-5">
            <div className="grid grid-cols-2 gap-3">
              <EntitlementRow label="Max Projects" value={String(entitlements.max_projects)} />
              <EntitlementRow label="Max Nodes/Project" value={String(entitlements.max_nodes_per_project)} />
              <EntitlementRow label="Sandbox Layers" value={String(entitlements.max_sandbox_layers)} />
              <EntitlementRow label="Monthly Simulations" value={String(entitlements.monthly_simulations)} />
              <BoolEntitlement label="ADR Generation" enabled={entitlements.can_generate_adr} />
              <BoolEntitlement label="Promote to PR" enabled={entitlements.can_promote_to_pr} />
              <BoolEntitlement label="Team Collaboration" enabled={entitlements.can_use_team_collaboration} />
              <BoolEntitlement label="Git Integration" enabled={entitlements.can_use_git_integration} />
              <BoolEntitlement label="SSO" enabled={entitlements.can_use_sso} />
              <BoolEntitlement label="Audit Logs" enabled={entitlements.can_use_audit_logs} />
            </div>
          </div>
        </section>

        {/* ── Upgrade CTA ─────────────────────────────────────────────── */}
        {plan !== 'enterprise' && (
          <div className="text-center py-6">
            <p className="text-sm text-slate-500 mb-3">
              Need more capacity or team features?
            </p>
            <Link
              to="/pricing"
              className="inline-block px-6 py-2.5 bg-canvas-accent text-white rounded-lg font-semibold text-sm hover:bg-canvas-accent/80 transition-colors"
            >
              View Plans
            </Link>
          </div>
        )}
      </main>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  active: 'text-status-pass',
  trialing: 'text-canvas-accent',
  past_due: 'text-status-fail',
  canceled: 'text-status-warn',
  incomplete: 'text-slate-500',
  paused: 'text-slate-500',
  expired: 'text-slate-600',
}

export function PlanBadge({ plan, size = 'normal' }: { plan: string; size?: 'small' | 'normal' }) {
  const colors: Record<string, string> = {
    free: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    pro: 'bg-canvas-accent/10 text-canvas-accent border-canvas-accent/20',
    team: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    enterprise: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  }
  const cls = colors[plan] ?? colors.free
  const sizeClass = size === 'small' ? 'text-[9px] px-1.5 py-0.5' : 'text-[11px] px-2 py-0.5'

  return (
    <span className={`${sizeClass} rounded-full border font-semibold uppercase ${cls}`}>
      {plan}
    </span>
  )
}

function UsageRow({ label, counter }: { label: string; counter: { used: number; limit: number } }) {
  const pct = counter.limit > 0 ? Math.round((counter.used / counter.limit) * 100) : 0
  const isHigh = pct >= 85
  const isOver = pct >= 100

  return (
    <div>
      <div className="flex justify-between text-[12px] mb-1">
        <span className="text-slate-400">{label}</span>
        <span className={`font-medium ${isOver ? 'text-status-fail' : isHigh ? 'text-status-warn' : 'text-slate-300'}`}>
          {counter.used} / {counter.limit}
        </span>
      </div>
      <div className="h-1.5 bg-canvas-bg rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            isOver ? 'bg-status-fail' : isHigh ? 'bg-status-warn' : 'bg-canvas-accent'
          }`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      {isHigh && !isOver && (
        <div className="text-[10px] text-status-warn mt-0.5">
          {pct}% used — approaching limit
        </div>
      )}
      {isOver && (
        <div className="text-[10px] text-status-fail mt-0.5">
          Limit reached. Upgrade to continue.
        </div>
      )}
    </div>
  )
}

function EntitlementRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-[12px]">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-300 font-medium">{value}</span>
    </div>
  )
}

function BoolEntitlement({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex justify-between text-[12px]">
      <span className="text-slate-500">{label}</span>
      {enabled ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-pass">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <span className="text-slate-600">-</span>
      )}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-bold text-slate-200 mb-3 uppercase tracking-wide">{children}</h2>
}

function Nav() {
  return (
    <nav className="h-14 border-b border-canvas-border flex items-center px-6 shrink-0 sticky top-0 z-50 bg-canvas-bg/80 backdrop-blur-sm">
      <Link to="/" className="text-canvas-accent font-bold font-mono text-lg">ArchTwin</Link>
      <div className="flex-1" />
      <Link to="/pricing" className="text-xs text-slate-400 hover:text-slate-200 mr-4">Pricing</Link>
      <Link to="/canvas" className="text-xs px-3 py-1.5 bg-canvas-accent text-white rounded-lg hover:bg-canvas-accent/80 transition-colors">
        Open Canvas
      </Link>
    </nav>
  )
}
