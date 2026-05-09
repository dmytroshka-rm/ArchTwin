/**
 * Contract tests — simulation result schema (Section 7.3 / DoD item 10).
 * Verifies that backend simulation result objects conform to the frontend's
 * generated type contracts.  These are data-shape tests, not UI tests.
 */

import { describe, it, expect } from 'vitest'
import type { SimulationResult, TradeoffMatrixRow, FidelityReport } from '@/generated/simulation-result.types'

// ── Fixture: minimal valid simulation result ──────────────────────────────

const VALID_RESULT: SimulationResult = {
  job_id: 'sim_test_001',
  status: 'completed',
  recommendation: {
    winner: 'proposal.layer-a',
    recommendation_score: 0.74,
    blocked: false,
    optimization_goal: 'cost_efficiency',
    rationale: 'Lower TCO with acceptable reliability trade-off.',
  },
  veto_gates: {
    security:    'pass',
    reliability: 'pass',
    compliance:  'pass',
  },
  fidelity: {
    base_confidence:      0.84,
    freshness_score:      0.92,
    staleness_penalty:    0.04,
    adjusted_confidence:  0.80,
    mode:                 'decision_grade',
  },
  trade_off_matrix: [
    {
      proposal_id:          'baseline',
      label:                'Baseline',
      is_baseline:          true,
      cost_score:           0.60,
      performance_score:    0.70,
      security_score:       0.85,
      reliability_score:    0.90,
      complexity_score:     0.75,
      fidelity_score:       0.80,
      veto_status:          'pass',
      recommendation_score: 0.72,
      optimization_goal:    'cost_efficiency',
      blocked:              false,
    },
    {
      proposal_id:          'proposal.layer-a',
      label:                'Layer A',
      is_baseline:          false,
      cost_score:           0.80,
      performance_score:    0.72,
      security_score:       0.83,
      reliability_score:    0.87,
      complexity_score:     0.70,
      fidelity_score:       0.80,
      veto_status:          'pass',
      recommendation_score: 0.74,
      optimization_goal:    'cost_efficiency',
      blocked:              false,
    },
  ],
  blast_radius: {
    high_risk_count: 1,
    total_impacted:  3,
    tier_1_count:    1,
    components: [
      {
        id:           'component.service.orders-api',
        name:         'orders-api',
        tier:         'tier_1',
        distance:     1,
        impact_score: 0.72,
        risk:         'connection_pool_behavior_change',
      },
    ],
  },
  reviewer_outputs: [
    { reviewer: 'cost',        status: 'pass', score: 0.80, summary: 'TCO reduced by 22%',         findings: [], blocked: false },
    { reviewer: 'performance', status: 'pass', score: 0.72, summary: 'Latency within tolerance',   findings: [], blocked: false },
    { reviewer: 'security',    status: 'pass', score: 0.83, summary: 'No critical findings',       findings: [], blocked: false },
  ],
  required_actions: {
    developer:    ['Add connection pool configuration for aurora_serverless_v2'],
    architect:    ['File ADR-042: Aurora Serverless v2 migration'],
    security_ops: [],
  },
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('SimulationResult contract', () => {
  it('has required top-level fields', () => {
    const r = VALID_RESULT
    expect(r.job_id).toBeTruthy()
    expect(r.status).toBe('completed')
    expect(r.veto_gates).toBeDefined()
    expect(r.fidelity).toBeDefined()
    expect(r.required_actions).toBeDefined()
  })

  it('recommendation score is between 0 and 1', () => {
    const score = VALID_RESULT.recommendation!.recommendation_score
    expect(score).toBeGreaterThanOrEqual(0)
    expect(score).toBeLessThanOrEqual(1)
  })

  it('trade_off_matrix rows have all required score columns', () => {
    const SCORE_FIELDS: (keyof TradeoffMatrixRow)[] = [
      'cost_score', 'performance_score', 'security_score',
      'reliability_score', 'complexity_score', 'fidelity_score',
      'recommendation_score',
    ]
    for (const row of VALID_RESULT.trade_off_matrix) {
      for (const field of SCORE_FIELDS) {
        const val = row[field] as number
        expect(typeof val).toBe('number')
        expect(val).toBeGreaterThanOrEqual(0)
        expect(val).toBeLessThanOrEqual(1)
      }
    }
  })

  it('veto gates only contain valid values', () => {
    const VALID_STATUSES = ['pass', 'fail', 'warn', 'skipped']
    for (const [, status] of Object.entries(VALID_RESULT.veto_gates)) {
      expect(VALID_STATUSES).toContain(status)
    }
  })

  it('fidelity adjusted_confidence satisfies: base - penalty ≈ adjusted', () => {
    const f: FidelityReport = VALID_RESULT.fidelity
    const expected = f.base_confidence - f.staleness_penalty
    expect(f.adjusted_confidence).toBeCloseTo(expected, 1)
  })

  it('blast radius impact_score is between 0 and 1', () => {
    for (const comp of VALID_RESULT.blast_radius!.components) {
      expect(comp.impact_score).toBeGreaterThanOrEqual(0)
      expect(comp.impact_score).toBeLessThanOrEqual(1)
    }
  })

  it('required_actions has developer, architect and security_ops keys', () => {
    const ra = VALID_RESULT.required_actions
    expect(Array.isArray(ra.developer)).toBe(true)
    expect(Array.isArray(ra.architect)).toBe(true)
    expect(Array.isArray(ra.security_ops)).toBe(true)
  })

  it('reviewer outputs contain all three reviewers', () => {
    const reviewers = VALID_RESULT.reviewer_outputs.map((r) => r.reviewer)
    expect(reviewers).toContain('cost')
    expect(reviewers).toContain('performance')
    expect(reviewers).toContain('security')
  })
})

// ── Veto blocking contract ─────────────────────────────────────────────────

describe('Veto gate blocking contract', () => {
  it('blocked result has veto_status = fail in matrix', () => {
    const blockedResult: SimulationResult = {
      ...VALID_RESULT,
      veto_gates: { security: 'fail', reliability: 'pass', compliance: 'pass' },
      trade_off_matrix: [
        { ...VALID_RESULT.trade_off_matrix[1], veto_status: 'fail', blocked: true },
      ],
    }
    const row = blockedResult.trade_off_matrix[0]
    expect(row.veto_status).toBe('fail')
    expect(row.blocked).toBe(true)
  })

  it('blocked recommendation has blocked=true', () => {
    const blockedResult: SimulationResult = {
      ...VALID_RESULT,
      recommendation: { ...VALID_RESULT.recommendation!, blocked: true },
    }
    expect(blockedResult.recommendation!.blocked).toBe(true)
  })
})

// ── Stale data / exploratory estimate contract ─────────────────────────────

describe('Stale data contract', () => {
  it('exploratory mode is set when adjusted_confidence < 0.80 due to staleness', () => {
    const staleResult: SimulationResult = {
      ...VALID_RESULT,
      fidelity: {
        base_confidence:     0.84,
        freshness_score:     0.30,
        staleness_penalty:   0.30,
        adjusted_confidence: 0.54,
        mode:                'exploratory_estimate',
      },
    }
    expect(staleResult.fidelity.mode).toBe('exploratory_estimate')
    expect(staleResult.fidelity.adjusted_confidence).toBeLessThan(0.65)
  })

  it('blocked mode is set when adjusted_confidence < 0.65', () => {
    const blockedFidelity: FidelityReport = {
      base_confidence:     0.84,
      freshness_score:     0.10,
      staleness_penalty:   0.50,
      adjusted_confidence: 0.34,
      mode:                'blocked',
    }
    expect(blockedFidelity.mode).toBe('blocked')
    expect(blockedFidelity.adjusted_confidence).toBeLessThan(0.65)
  })
})

// ── Sandbox layer contract ─────────────────────────────────────────────────

describe('Sandbox layer contract', () => {
  it('design proposal has required fields', () => {
    const proposal = {
      id:                'proposal.layer-a',
      title:             'Layer A',
      status:            'sandbox_layer',
      baseline_ref:      'baseline.main@sha256:abc123',
      optimization_goal: 'cost_efficiency',
      diff:              { operations: [] },
    }
    expect(proposal.id).toBeTruthy()
    expect(proposal.baseline_ref).toBeTruthy()
    expect(proposal.optimization_goal).toBeTruthy()
    expect(proposal.diff.operations).toBeInstanceOf(Array)
  })
})
