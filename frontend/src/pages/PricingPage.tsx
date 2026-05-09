import { Link } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { useBillingStore } from '@/store/billingStore'
import { billingApi } from '@/api/endpoints'

// ── Plan data ─────────────────────────────────────────────────────────────────

interface PlanInfo {
  key: string
  name: string
  tagline: string
  monthlyPrice: number | null
  yearlyPrice: number | null
  features: string[]
  limits: { label: string; value: string }[]
  cta: string
  highlighted?: boolean
  color: string
}

const PLANS: PlanInfo[] = [
  {
    key: 'free',
    name: 'Free',
    tagline: 'Explore ArchTwin with the demo Canvas',
    monthlyPrice: 0,
    yearlyPrice: 0,
    features: [
      'Demo Canvas access',
      'YAML import',
      'Basic simulation (10/mo)',
      'Single project',
    ],
    limits: [
      { label: 'Projects', value: '1' },
      { label: 'Nodes', value: '15' },
      { label: 'Sandbox Layers', value: '1' },
      { label: 'Simulations', value: '10/mo' },
    ],
    cta: 'Start Free',
    color: 'slate',
  },
  {
    key: 'pro',
    name: 'Pro',
    tagline: 'For individual architects and tech leads',
    monthlyPrice: 29,
    yearlyPrice: 279,
    features: [
      'Everything in Free',
      'ADR draft generation',
      'Multiple projects (10)',
      'Extended simulations (300/mo)',
      'What-if layers (5)',
      'Export reports',
    ],
    limits: [
      { label: 'Projects', value: '10' },
      { label: 'Nodes', value: '100' },
      { label: 'Sandbox Layers', value: '5' },
      { label: 'Simulations', value: '300/mo' },
    ],
    cta: 'Upgrade to Pro',
    highlighted: true,
    color: 'blue',
  },
  {
    key: 'team',
    name: 'Team',
    tagline: 'For engineering teams with shared workflows',
    monthlyPrice: 79,
    yearlyPrice: 759,
    features: [
      'Everything in Pro',
      'Team collaboration',
      'Promote to PR (Git)',
      'Git integration',
      'Comments & reviews',
      'Shared workspace',
    ],
    limits: [
      { label: 'Projects', value: '50' },
      { label: 'Nodes', value: '500' },
      { label: 'Sandbox Layers', value: '20' },
      { label: 'Simulations', value: '3,000/mo' },
    ],
    cta: 'Start Team Plan',
    color: 'purple',
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    tagline: 'For organizations with custom requirements',
    monthlyPrice: null,
    yearlyPrice: null,
    features: [
      'Everything in Team',
      'SSO / SAML',
      'Audit logs',
      'Self-hosted scanner',
      'Custom security policies',
      'Private deployment',
      'Dedicated support',
    ],
    limits: [
      { label: 'Projects', value: 'Unlimited' },
      { label: 'Nodes', value: 'Unlimited' },
      { label: 'Sandbox Layers', value: 'Unlimited' },
      { label: 'Simulations', value: 'Unlimited' },
    ],
    cta: 'Contact Sales',
    color: 'amber',
  },
]

export function PricingPage() {
  const [interval, setInterval] = useState<'monthly' | 'yearly'>('monthly')
  const { plan: currentPlan } = useBillingStore()

  // Load subscription on mount
  useEffect(() => {
    billingApi.getSubscription().then((info) => {
      useBillingStore.getState().setSubscription(info)
    }).catch(() => { /* ignore */ })
  }, [])

  const handleUpgrade = useCallback(async (planKey: string) => {
    if (planKey === 'enterprise') {
      window.open('mailto:sales@archtwin.dev?subject=Enterprise%20Plan', '_blank')
      return
    }
    try {
      const key = `${planKey}_${interval}`
      const { checkout_url } = await billingApi.createCheckout(key)
      window.location.href = checkout_url
    } catch (err) {
      console.error('Checkout failed:', err)
    }
  }, [interval])

  return (
    <div className="min-h-screen bg-canvas-bg flex flex-col">
      <Nav />

      <main className="flex-1 px-6 py-16">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-2xl font-bold text-slate-100 mb-2">Choose your plan</h1>
            <p className="text-sm text-slate-500 mb-6">
              Start free. Upgrade when your architecture needs grow.
            </p>

            {/* Interval toggle */}
            <div className="inline-flex items-center bg-canvas-surface border border-canvas-border rounded-lg p-1">
              <button
                onClick={() => setInterval('monthly')}
                className={`text-[12px] px-4 py-1.5 rounded-md transition-colors ${
                  interval === 'monthly'
                    ? 'bg-canvas-accent/15 text-canvas-accent font-medium'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                Monthly
              </button>
              <button
                onClick={() => setInterval('yearly')}
                className={`text-[12px] px-4 py-1.5 rounded-md transition-colors ${
                  interval === 'yearly'
                    ? 'bg-canvas-accent/15 text-canvas-accent font-medium'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                Yearly <span className="text-status-pass text-[10px] ml-1">Save 20%</span>
              </button>
            </div>
          </div>

          {/* Plan cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {PLANS.map((p) => (
              <PlanCard
                key={p.key}
                plan={p}
                interval={interval}
                isCurrent={currentPlan === p.key}
                onSelect={() => handleUpgrade(p.key)}
              />
            ))}
          </div>

          {/* Feature comparison */}
          <div className="mt-16">
            <h2 className="text-lg font-bold text-slate-200 text-center mb-8">Feature comparison</h2>
            <FeatureTable currentPlan={currentPlan} />
          </div>

          {/* FAQ */}
          <div className="mt-16 max-w-2xl mx-auto">
            <h2 className="text-lg font-bold text-slate-200 text-center mb-6">Questions</h2>
            <div className="space-y-3">
              <FaqItem
                q="Can I try ArchTwin before paying?"
                a="Yes. The Free plan gives you access to the demo Canvas, YAML import, and 10 simulations per month. No credit card required."
              />
              <FaqItem
                q="What happens when I hit a limit?"
                a="You'll see a clear message explaining the limit and which plan unlocks more. Your existing work is never deleted."
              />
              <FaqItem
                q="Can I downgrade?"
                a="Yes. When you downgrade, you keep access until the end of your billing period. Existing projects become read-only if they exceed the new plan's limits."
              />
              <FaqItem
                q="What about Enterprise pricing?"
                a="Enterprise plans are custom. Contact our team for pricing based on your requirements: SSO, audit logs, private deployment, and more."
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PlanCard({ plan, interval, isCurrent, onSelect }: {
  plan: PlanInfo; interval: 'monthly' | 'yearly'; isCurrent: boolean; onSelect: () => void
}) {
  const price = interval === 'monthly' ? plan.monthlyPrice : plan.yearlyPrice
  const perMonth = price !== null
    ? interval === 'yearly' ? Math.round(price / 12) : price
    : null

  const borderColor = plan.highlighted
    ? 'border-canvas-accent/40'
    : isCurrent
    ? 'border-status-pass/40'
    : 'border-canvas-border'

  return (
    <div className={`relative bg-canvas-surface/40 border ${borderColor} rounded-xl p-5 flex flex-col`}>
      {plan.highlighted && (
        <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[10px] font-semibold bg-canvas-accent text-white px-3 py-0.5 rounded-full">
          Most Popular
        </div>
      )}
      {isCurrent && (
        <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[10px] font-semibold bg-status-pass text-white px-3 py-0.5 rounded-full">
          Current Plan
        </div>
      )}

      <h3 className="text-sm font-bold text-slate-200 mb-1">{plan.name}</h3>
      <p className="text-[11px] text-slate-500 mb-4">{plan.tagline}</p>

      {/* Price */}
      <div className="mb-4">
        {perMonth !== null ? (
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold text-slate-100">${perMonth}</span>
            <span className="text-[11px] text-slate-500">/mo</span>
          </div>
        ) : (
          <div className="text-lg font-bold text-slate-300">Custom</div>
        )}
        {interval === 'yearly' && price !== null && price > 0 && (
          <div className="text-[10px] text-slate-600 mt-0.5">${price} billed yearly</div>
        )}
      </div>

      {/* Limits */}
      <div className="space-y-1.5 mb-4">
        {plan.limits.map((l) => (
          <div key={l.label} className="flex justify-between text-[11px]">
            <span className="text-slate-500">{l.label}</span>
            <span className="text-slate-300 font-medium">{l.value}</span>
          </div>
        ))}
      </div>

      {/* Features */}
      <div className="space-y-1 mb-5 flex-1">
        {plan.features.map((f) => (
          <div key={f} className="flex items-start gap-1.5 text-[11px] text-slate-400">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-status-pass shrink-0 mt-0.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            {f}
          </div>
        ))}
      </div>

      {/* CTA */}
      <button
        onClick={onSelect}
        disabled={isCurrent}
        className={`w-full py-2 rounded-lg text-[12px] font-semibold transition-colors ${
          isCurrent
            ? 'bg-canvas-surface border border-canvas-border text-slate-500 cursor-default'
            : plan.highlighted
            ? 'bg-canvas-accent text-white hover:bg-canvas-accent/80'
            : 'bg-canvas-surface border border-canvas-border text-slate-300 hover:border-slate-500'
        }`}
      >
        {isCurrent ? 'Current Plan' : plan.cta}
      </button>
    </div>
  )
}

function FeatureTable({ currentPlan }: { currentPlan: string }) {
  const rows: { feature: string; free: string; pro: string; team: string; enterprise: string }[] = [
    { feature: 'Projects', free: '1', pro: '10', team: '50', enterprise: 'Unlimited' },
    { feature: 'Nodes per project', free: '15', pro: '100', team: '500', enterprise: 'Unlimited' },
    { feature: 'Sandbox layers', free: '1', pro: '5', team: '20', enterprise: 'Unlimited' },
    { feature: 'Monthly simulations', free: '10', pro: '300', team: '3,000', enterprise: 'Unlimited' },
    { feature: 'YAML import/export', free: 'Y', pro: 'Y', team: 'Y', enterprise: 'Y' },
    { feature: 'ADR generation', free: '-', pro: 'Y', team: 'Y', enterprise: 'Y' },
    { feature: 'Promote to PR', free: '-', pro: '-', team: 'Y', enterprise: 'Y' },
    { feature: 'Team collaboration', free: '-', pro: '-', team: 'Y', enterprise: 'Y' },
    { feature: 'Git integration', free: '-', pro: '-', team: 'Y', enterprise: 'Y' },
    { feature: 'SSO / SAML', free: '-', pro: '-', team: '-', enterprise: 'Y' },
    { feature: 'Audit logs', free: '-', pro: '-', team: '-', enterprise: 'Y' },
    { feature: 'Dedicated support', free: '-', pro: '-', team: '-', enterprise: 'Y' },
  ]

  const planCols = ['free', 'pro', 'team', 'enterprise'] as const
  const colLabels = { free: 'Free', pro: 'Pro', team: 'Team', enterprise: 'Enterprise' }

  return (
    <div className="bg-canvas-surface/30 border border-canvas-border rounded-xl overflow-hidden">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-canvas-border">
            <th className="text-left py-2.5 px-4 text-slate-500 font-medium">Feature</th>
            {planCols.map((p) => (
              <th
                key={p}
                className={`text-center py-2.5 px-3 font-medium ${
                  currentPlan === p ? 'text-canvas-accent' : 'text-slate-400'
                }`}
              >
                {colLabels[p]}
                {currentPlan === p && <span className="block text-[9px] text-status-pass">current</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.feature} className="border-b border-canvas-border/40 last:border-0">
              <td className="py-2 px-4 text-slate-400">{row.feature}</td>
              {planCols.map((p) => {
                const val = row[p]
                return (
                  <td key={p} className="text-center py-2 px-3">
                    {val === 'Y' ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-pass inline">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : val === '-' ? (
                      <span className="text-slate-600">-</span>
                    ) : (
                      <span className="text-slate-300">{val}</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-canvas-surface/30 border border-canvas-border rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-[12px] text-slate-300 font-medium">{q}</span>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`text-slate-500 transition-transform ${open ? 'rotate-90' : ''}`}
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>
      {open && (
        <div className="px-4 pb-3 text-[12px] text-slate-500 leading-relaxed">{a}</div>
      )}
    </div>
  )
}

function Nav() {
  return (
    <nav className="h-14 border-b border-canvas-border flex items-center px-6 shrink-0 sticky top-0 z-50 bg-canvas-bg/80 backdrop-blur-sm">
      <Link to="/" className="text-canvas-accent font-bold font-mono text-lg">ArchTwin</Link>
      <div className="flex-1" />
      <Link to="/about" className="text-xs text-slate-400 hover:text-slate-200 mr-4">About</Link>
      <Link to="/instructions" className="text-xs text-slate-400 hover:text-slate-200 mr-4">Docs</Link>
      <Link to="/canvas" className="text-xs px-3 py-1.5 bg-canvas-accent text-white rounded-lg hover:bg-canvas-accent/80 transition-colors">
        Open Canvas
      </Link>
    </nav>
  )
}
