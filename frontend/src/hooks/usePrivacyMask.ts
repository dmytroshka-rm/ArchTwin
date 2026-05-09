/**
 * usePrivacyMask — Section 9.1 Data handling rules.
 * Cloud ARNs, Account IDs and resource IDs are masked unless the user
 * has the `canViewSensitive` permission.
 *
 * Copy-to-clipboard is disabled for sensitive-looking values by default.
 */

import { usePermissions } from './usePermissions'

// Patterns that identify sensitive values
const SENSITIVE_PATTERNS = [
  /arn:aws:[a-z0-9:/-]+/i,                 // AWS ARN
  /\b\d{12}\b/,                             // AWS account ID (12 digits)
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,  // UUID / GCP project
  /projects\/[a-z0-9-]+\/[a-z]+\/[^"'\s]+/i, // GCP resource path
  /subscriptions\/[a-f0-9-]{36}/i,          // Azure subscription ID
]

function isSensitive(value: string): boolean {
  return SENSITIVE_PATTERNS.some((p) => p.test(value))
}

function maskValue(value: string): string {
  // Replace matching segments with *** prefix + last 4 chars
  return value.replace(
    /arn:aws:[a-z0-9:/-]+|[0-9]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
    (match) => `***…${match.slice(-4)}`,
  )
}

export interface MaskedValue {
  display: string
  raw: string
  masked: boolean
  copyEnabled: boolean
}

export function usePrivacyMask() {
  const { canViewSensitive } = usePermissions()

  function mask(value: string): MaskedValue {
    const sensitive = isSensitive(value)
    return {
      raw:         value,
      display:     (sensitive && !canViewSensitive) ? maskValue(value) : value,
      masked:      sensitive && !canViewSensitive,
      copyEnabled: !sensitive || canViewSensitive,
    }
  }

  return { mask, canViewSensitive }
}
