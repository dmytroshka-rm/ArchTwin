/**
 * Billing & subscription types — plans, entitlements, usage.
 * Backend is the single source of truth for all billing decisions.
 */

// ── Plan keys ─────────────────────────────────────────────────────────────────

export type PlanKey = 'free' | 'pro' | 'team' | 'enterprise'

export type BillingInterval = 'monthly' | 'yearly'

export type SubscriptionStatus =
  | 'trialing'
  | 'active'
  | 'past_due'
  | 'canceled'
  | 'incomplete'
  | 'paused'
  | 'expired'

// ── Plan definition ───────────────────────────────────────────────────────────

export interface Plan {
  plan_key: PlanKey
  name: string
  billing_interval: BillingInterval
  price_cents: number
  currency: string
  is_active: boolean
}

// ── Entitlements ──────────────────────────────────────────────────────────────

export interface Entitlements {
  max_projects: number
  max_nodes_per_project: number
  max_sandbox_layers: number
  monthly_simulations: number
  can_export_yaml: boolean
  can_generate_adr: boolean
  can_promote_to_pr: boolean
  can_use_team_collaboration: boolean
  can_use_git_integration: boolean
  can_use_sso: boolean
  can_use_audit_logs: boolean
  can_use_self_hosted_scanner: boolean
  can_use_custom_policies: boolean
}

// ── Usage counter ─────────────────────────────────────────────────────────────

export interface UsageCounter {
  used: number
  limit: number
}

export interface UsageCounters {
  simulations_run: UsageCounter
  projects_created: UsageCounter
  sandbox_layers_created: UsageCounter
  adr_generated: UsageCounter
  yaml_exports: UsageCounter
}

// ── Subscription response ─────────────────────────────────────────────────────

export interface SubscriptionInfo {
  workspace_id: string
  plan: PlanKey
  status: SubscriptionStatus
  current_period_end: string | null
  cancel_at_period_end: boolean
  trial_ends_at: string | null
  entitlements: Entitlements
  usage: UsageCounters
}

// ── Entitlement check ─────────────────────────────────────────────────────────

export interface EntitlementCheck {
  allowed: boolean
  plan: PlanKey
  reason: string | null
  upgrade_required?: boolean
  recommended_plan?: PlanKey
}

// ── Checkout / Portal ─────────────────────────────────────────────────────────

export interface CheckoutResponse {
  checkout_url: string
}

export interface PortalResponse {
  portal_url: string
}

// ── Plan display info (for Pricing page) ──────────────────────────────────────

export interface PlanDisplay {
  key: PlanKey
  name: string
  tagline: string
  monthlyPrice: number | null  // null = custom/contact sales
  yearlyPrice: number | null
  features: string[]
  limits: Record<string, string>
  cta: string
  highlighted?: boolean
}
