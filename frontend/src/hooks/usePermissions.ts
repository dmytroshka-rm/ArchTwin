/**
 * usePermissions — Section 9.2 Role-based permissions.
 * In production this would come from an auth context / JWT claims.
 * The hook provides a unified gate so all component code calls the same check.
 */

export type UserRole = 'developer' | 'architect' | 'security_ops' | 'viewer'

export interface Permissions {
  canEdit:          boolean   // create / update components and relations
  canRunSimulation: boolean   // trigger simulation jobs
  canPromote:       boolean   // request promotion artifacts
  canArchiveLayer:  boolean   // archive / delete sandbox layers
  canApproveReview: boolean   // approve review-requested proposals
  canViewSensitive: boolean   // see unmasked ARNs / account IDs (Section 9.1)
}

const ROLE_PERMS: Record<UserRole, Permissions> = {
  developer: {
    canEdit:          true,
    canRunSimulation: true,
    canPromote:       false,
    canArchiveLayer:  false,
    canApproveReview: false,
    canViewSensitive: false,
  },
  architect: {
    canEdit:          true,
    canRunSimulation: true,
    canPromote:       true,
    canArchiveLayer:  true,
    canApproveReview: true,
    canViewSensitive: true,
  },
  security_ops: {
    canEdit:          false,
    canRunSimulation: true,
    canPromote:       false,
    canArchiveLayer:  false,
    canApproveReview: true,
    canViewSensitive: true,
  },
  viewer: {
    canEdit:          false,
    canRunSimulation: false,
    canPromote:       false,
    canArchiveLayer:  false,
    canApproveReview: false,
    canViewSensitive: false,
  },
}

/** In a real app: read role from auth context / JWT. */
function getCurrentRole(): UserRole {
  const stored = (typeof window !== 'undefined'
    ? window.sessionStorage.getItem('isa_cad_role')
    : null) as UserRole | null
  return stored ?? 'developer'
}

export function usePermissions(): Permissions {
  const role = getCurrentRole()
  return ROLE_PERMS[role] ?? ROLE_PERMS.viewer
}
