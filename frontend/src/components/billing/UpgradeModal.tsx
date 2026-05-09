/**
 * UpgradeModal — shown when a user tries to use a feature gated by their plan.
 * Reads state from billingStore, drives checkout via billingApi.
 */

import { useCallback } from 'react'
import { useBillingStore } from '@/store/billingStore'
import { billingApi } from '@/api/endpoints'

const FEATURE_LABELS: Record<string, string> = {
  can_generate_adr: 'Generate ADR drafts',
  can_promote_to_pr: 'Promote architecture changes to Git PR',
  can_use_team_collaboration: 'Team collaboration and shared workspaces',
  can_use_git_integration: 'Git integration for architecture changes',
  can_use_sso: 'Single Sign-On (SSO / SAML)',
  can_use_audit_logs: 'Audit logging for compliance',
  can_use_self_hosted_scanner: 'Self-hosted security scanner',
  can_use_custom_policies: 'Custom security and compliance policies',
  monthly_simulations: 'Run more simulations per month',
  max_projects: 'Create more projects',
  max_sandbox_layers: 'Create more sandbox layers',
  max_nodes_per_project: 'Add more components per project',
}

const PLAN_NAMES: Record<string, string> = {
  free: 'Free',
  pro: 'Pro',
  team: 'Team',
  enterprise: 'Enterprise',
}

export function UpgradeModal() {
  const {
    upgradeModalOpen,
    upgradeModalFeature,
    upgradeModalPlan,
    closeUpgradeModal,
  } = useBillingStore()

  const handleUpgrade = useCallback(async () => {
    if (!upgradeModalPlan || upgradeModalPlan === 'enterprise') {
      window.open('mailto:sales@archtwin.dev?subject=Enterprise%20Plan', '_blank')
      closeUpgradeModal()
      return
    }
    try {
      const { checkout_url } = await billingApi.createCheckout(`${upgradeModalPlan}_monthly`)
      closeUpgradeModal()
      window.location.href = checkout_url
    } catch (err) {
      console.error('Checkout failed:', err)
    }
  }, [upgradeModalPlan, closeUpgradeModal])

  const handleViewPlans = useCallback(() => {
    closeUpgradeModal()
    window.location.href = '/pricing'
  }, [closeUpgradeModal])

  if (!upgradeModalOpen) return null

  const featureLabel = upgradeModalFeature
    ? FEATURE_LABELS[upgradeModalFeature] ?? upgradeModalFeature
    : 'this feature'
  const planName = upgradeModalPlan ? PLAN_NAMES[upgradeModalPlan] ?? upgradeModalPlan : 'Pro'

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={closeUpgradeModal} />

      {/* Modal */}
      <div className="relative bg-canvas-surface border border-canvas-border rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
        {/* Close button */}
        <button
          onClick={closeUpgradeModal}
          className="absolute top-3 right-3 text-slate-500 hover:text-slate-300 transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {/* Icon */}
        <div className="w-12 h-12 rounded-xl bg-canvas-accent/10 border border-canvas-accent/20 flex items-center justify-center mx-auto mb-4">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-canvas-accent">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>

        <h2 className="text-lg font-bold text-slate-100 text-center mb-1">Upgrade required</h2>
        <p className="text-sm text-slate-400 text-center mb-5">
          This feature is available on the <span className="text-canvas-accent font-medium">{planName}</span> plan.
        </p>

        {/* Feature detail */}
        <div className="bg-canvas-bg/80 border border-canvas-border rounded-lg px-4 py-3 mb-6">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Feature</div>
          <div className="text-sm text-slate-200">{featureLabel}</div>
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={handleUpgrade}
            className="flex-1 py-2.5 bg-canvas-accent text-white rounded-lg font-semibold text-sm hover:bg-canvas-accent/80 transition-colors"
          >
            Upgrade to {planName}
          </button>
          <button
            onClick={handleViewPlans}
            className="px-4 py-2.5 border border-canvas-border text-slate-300 rounded-lg text-sm hover:border-slate-500 transition-colors"
          >
            View plans
          </button>
        </div>
      </div>
    </div>
  )
}
