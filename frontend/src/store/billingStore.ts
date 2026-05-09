/**
 * Billing store — tracks subscription state, entitlements, and usage.
 * All data comes from backend; frontend only caches and displays.
 */

import { create } from 'zustand'
import type {
  PlanKey,
  SubscriptionStatus,
  Entitlements,
  UsageCounters,
  SubscriptionInfo,
  EntitlementCheck,
} from '@/generated/billing.types'

// ── Default free entitlements ─────────────────────────────────────────────────

const FREE_ENTITLEMENTS: Entitlements = {
  max_projects: 1,
  max_nodes_per_project: 15,
  max_sandbox_layers: 1,
  monthly_simulations: 10,
  can_export_yaml: true,
  can_generate_adr: false,
  can_promote_to_pr: false,
  can_use_team_collaboration: false,
  can_use_git_integration: false,
  can_use_sso: false,
  can_use_audit_logs: false,
  can_use_self_hosted_scanner: false,
  can_use_custom_policies: false,
}

const EMPTY_USAGE: UsageCounters = {
  simulations_run: { used: 0, limit: 10 },
  projects_created: { used: 0, limit: 1 },
  sandbox_layers_created: { used: 0, limit: 1 },
  adr_generated: { used: 0, limit: 0 },
  yaml_exports: { used: 0, limit: 100 },
}

interface BillingState {
  // Subscription info
  plan: PlanKey
  status: SubscriptionStatus
  currentPeriodEnd: string | null
  cancelAtPeriodEnd: boolean
  trialEndsAt: string | null
  workspaceId: string | null

  // Entitlements & usage
  entitlements: Entitlements
  usage: UsageCounters

  // Loading state
  loaded: boolean
  loading: boolean
  error: string | null

  // Upgrade modal
  upgradeModalOpen: boolean
  upgradeModalFeature: string | null
  upgradeModalPlan: PlanKey | null

  // Actions
  setSubscription: (info: SubscriptionInfo) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  openUpgradeModal: (feature: string, recommendedPlan?: PlanKey) => void
  closeUpgradeModal: () => void
  checkFeature: (feature: keyof Entitlements) => EntitlementCheck
  isFeatureAllowed: (feature: keyof Entitlements) => boolean
  getUsagePercent: (metric: keyof UsageCounters) => number
  reset: () => void
}

export const useBillingStore = create<BillingState>((set, get) => ({
  plan: 'free',
  status: 'active',
  currentPeriodEnd: null,
  cancelAtPeriodEnd: false,
  trialEndsAt: null,
  workspaceId: null,
  entitlements: FREE_ENTITLEMENTS,
  usage: EMPTY_USAGE,
  loaded: false,
  loading: false,
  error: null,
  upgradeModalOpen: false,
  upgradeModalFeature: null,
  upgradeModalPlan: null,

  setSubscription: (info) =>
    set({
      plan: info.plan,
      status: info.status,
      currentPeriodEnd: info.current_period_end,
      cancelAtPeriodEnd: info.cancel_at_period_end,
      trialEndsAt: info.trial_ends_at,
      workspaceId: info.workspace_id,
      entitlements: info.entitlements,
      usage: info.usage,
      loaded: true,
      loading: false,
      error: null,
    }),

  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),

  openUpgradeModal: (feature, recommendedPlan) =>
    set({
      upgradeModalOpen: true,
      upgradeModalFeature: feature,
      upgradeModalPlan: recommendedPlan ?? 'pro',
    }),

  closeUpgradeModal: () =>
    set({
      upgradeModalOpen: false,
      upgradeModalFeature: null,
      upgradeModalPlan: null,
    }),

  checkFeature: (feature) => {
    const { entitlements, plan } = get()
    const value = entitlements[feature]
    if (typeof value === 'boolean') {
      if (value) return { allowed: true, plan, reason: null }
      const rec = FEATURE_PLAN_MAP[feature] ?? 'pro'
      return {
        allowed: false,
        plan,
        reason: `Feature requires ${rec.charAt(0).toUpperCase() + rec.slice(1)} plan or higher`,
        upgrade_required: true,
        recommended_plan: rec,
      }
    }
    return { allowed: true, plan, reason: null }
  },

  isFeatureAllowed: (feature) => {
    const value = get().entitlements[feature]
    return typeof value === 'boolean' ? value : true
  },

  getUsagePercent: (metric) => {
    const counter = get().usage[metric]
    if (!counter || counter.limit === 0) return 0
    return Math.round((counter.used / counter.limit) * 100)
  },

  reset: () =>
    set({
      plan: 'free',
      status: 'active',
      currentPeriodEnd: null,
      cancelAtPeriodEnd: false,
      trialEndsAt: null,
      workspaceId: null,
      entitlements: FREE_ENTITLEMENTS,
      usage: EMPTY_USAGE,
      loaded: false,
      loading: false,
      error: null,
    }),
}))

// Maps features to the minimum plan that unlocks them
const FEATURE_PLAN_MAP: Partial<Record<keyof Entitlements, PlanKey>> = {
  can_generate_adr: 'pro',
  can_promote_to_pr: 'team',
  can_use_team_collaboration: 'team',
  can_use_git_integration: 'team',
  can_use_sso: 'enterprise',
  can_use_audit_logs: 'enterprise',
  can_use_self_hosted_scanner: 'enterprise',
  can_use_custom_policies: 'enterprise',
}
