/**
 * Contract tests — privacy masking (Section 9.1).
 * Verifies that sensitive values (ARNs, account IDs, UUIDs) are masked
 * for non-privileged users and exposed to users with canViewSensitive.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePrivacyMask } from '@/hooks/usePrivacyMask'
import * as permsModule from '@/hooks/usePermissions'

describe('usePrivacyMask — sensitive value masking', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  function makeHook(canViewSensitive: boolean) {
    vi.spyOn(permsModule, 'usePermissions').mockReturnValue({
      canEdit:          false,
      canRunSimulation: false,
      canPromote:       false,
      canArchiveLayer:  false,
      canApproveReview: false,
      canViewSensitive,
    })
    return renderHook(() => usePrivacyMask()).result.current
  }

  it('masks AWS ARN for non-privileged user', () => {
    const { mask } = makeHook(false)
    const result = mask('arn:aws:s3:::my-bucket-name')
    expect(result.masked).toBe(true)
    expect(result.display).not.toBe('arn:aws:s3:::my-bucket-name')
    expect(result.display).toContain('***')
  })

  it('shows AWS ARN to privileged user', () => {
    const { mask } = makeHook(true)
    const result = mask('arn:aws:s3:::my-bucket-name')
    expect(result.masked).toBe(false)
    expect(result.display).toBe('arn:aws:s3:::my-bucket-name')
  })

  it('masks 12-digit AWS account ID', () => {
    const { mask } = makeHook(false)
    const result = mask('Account: 123456789012')
    expect(result.masked).toBe(true)
    expect(result.copyEnabled).toBe(false)
  })

  it('does not mask regular text', () => {
    const { mask } = makeHook(false)
    const result = mask('aurora_serverless_v2')
    expect(result.masked).toBe(false)
    expect(result.display).toBe('aurora_serverless_v2')
    expect(result.copyEnabled).toBe(true)
  })

  it('copy is disabled for sensitive values when not privileged', () => {
    const { mask } = makeHook(false)
    const result = mask('arn:aws:iam::123456789012:role/admin')
    expect(result.copyEnabled).toBe(false)
  })

  it('copy is enabled for sensitive values when privileged', () => {
    const { mask } = makeHook(true)
    const result = mask('arn:aws:iam::123456789012:role/admin')
    expect(result.copyEnabled).toBe(true)
  })
})
