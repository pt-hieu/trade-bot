import { describe, it, expect } from 'vitest'
import { buildWeightedReturns } from '../risk-metrics'

describe('buildWeightedReturns', () => {
  it('computes weighted average returns across tickers', () => {
    const weights = { VHM: 0.6, NLG: 0.4 }
    const tickerReturns = new Map([
      ['VHM', new Map([['2026-01-01', 0.02], ['2026-01-02', -0.01]])],
      ['NLG', new Map([['2026-01-01', 0.01], ['2026-01-02', 0.03]])],
    ])
    const result = buildWeightedReturns(weights, tickerReturns)
    // Day 1: (0.6*0.02 + 0.4*0.01) / 1.0 = 0.016
    expect(result.get('2026-01-01')).toBeCloseTo(0.016)
    // Day 2: (0.6*(-0.01) + 0.4*0.03) / 1.0 = 0.006
    expect(result.get('2026-01-02')).toBeCloseTo(0.006)
  })

  it('normalizes by covered weight when a ticker is missing on a date', () => {
    const weights = { VHM: 0.6, NLG: 0.4 }
    const tickerReturns = new Map([
      ['VHM', new Map([['2026-01-01', 0.02], ['2026-01-02', 0.05]])],
      ['NLG', new Map([['2026-01-01', 0.01]])],
    ])
    const result = buildWeightedReturns(weights, tickerReturns)
    // Day 1: both present, normal weighted avg
    expect(result.get('2026-01-01')).toBeCloseTo(0.016)
    // Day 2: only VHM (60% >= 50% threshold), normalized: (0.6*0.05) / 0.6 = 0.05
    expect(result.get('2026-01-02')).toBeCloseTo(0.05)
  })

  it('skips dates where coverage falls below 50%', () => {
    const weights = { VHM: 0.6, NLG: 0.4 }
    const tickerReturns = new Map([
      ['VHM', new Map([['2026-01-01', 0.02]])],
      ['NLG', new Map([['2026-01-01', 0.01], ['2026-01-02', 0.03]])],
    ])
    const result = buildWeightedReturns(weights, tickerReturns)
    // Day 1: both present
    expect(result.has('2026-01-01')).toBe(true)
    // Day 2: only NLG (40% weight < 50% threshold) → excluded
    expect(result.has('2026-01-02')).toBe(false)
  })

  it('returns empty map when no ticker returns match weights', () => {
    const weights = { FPT: 1.0 }
    const tickerReturns = new Map([
      ['VHM', new Map([['2026-01-01', 0.02]])],
    ])
    const result = buildWeightedReturns(weights, tickerReturns)
    expect(result.size).toBe(0)
  })

  it('returns empty map when weights are empty', () => {
    const tickerReturns = new Map([
      ['VHM', new Map([['2026-01-01', 0.02]])],
    ])
    const result = buildWeightedReturns({}, tickerReturns)
    expect(result.size).toBe(0)
  })

  it('returns empty map when tickerReturns are empty', () => {
    const weights = { VHM: 1.0 }
    const result = buildWeightedReturns(weights, new Map())
    expect(result.size).toBe(0)
  })

  it('returns dates in sorted order', () => {
    const weights = { VHM: 1.0 }
    const tickerReturns = new Map([
      ['VHM', new Map([['2026-01-03', 0.01], ['2026-01-01', 0.02], ['2026-01-02', 0.03]])],
    ])
    const result = buildWeightedReturns(weights, tickerReturns)
    const dates = [...result.keys()]
    expect(dates).toEqual(['2026-01-01', '2026-01-02', '2026-01-03'])
  })
})
