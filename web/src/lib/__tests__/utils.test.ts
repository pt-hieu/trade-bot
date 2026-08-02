import { describe, it, expect } from 'vitest'
import { formatVND, formatPct, formatCompact } from '../utils'

describe('formatVND', () => {
  it('formats positive numbers as VND currency', () => {
    const result = formatVND(26600000)
    expect(result).toContain('26')
    expect(result).toContain('600')
    expect(result).toContain('000')
  })

  it('formats zero', () => {
    const result = formatVND(0)
    expect(result).toContain('0')
  })

  it('formats negative numbers', () => {
    const result = formatVND(-500000)
    expect(result).toContain('500')
  })

  it('handles string numbers', () => {
    const result = formatVND('1000000')
    expect(result).toContain('1')
    expect(result).toContain('000')
  })

  it('returns dash for null', () => {
    expect(formatVND(null)).toBe('—')
  })

  it('returns dash for undefined', () => {
    expect(formatVND(undefined)).toBe('—')
  })

  it('returns dash for NaN string', () => {
    expect(formatVND('abc')).toBe('—')
  })

  it('formats empty string as zero', () => {
    // Number('') === 0 in JS, so it formats as zero
    const result = formatVND('')
    expect(result).toContain('0')
  })
})

describe('formatPct', () => {
  it('formats positive percentage with + sign', () => {
    expect(formatPct(5.5)).toBe('+5.50%')
  })

  it('formats negative percentage', () => {
    expect(formatPct(-3.14)).toBe('-3.14%')
  })

  it('formats zero', () => {
    expect(formatPct(0)).toBe('+0.00%')
  })

  it('formats with 2 decimal places', () => {
    expect(formatPct(1)).toBe('+1.00%')
    expect(formatPct(1.1)).toBe('+1.10%')
    expect(formatPct(1.125)).toBe('+1.13%')  // rounds up
  })

  it('handles string input', () => {
    expect(formatPct('2.5')).toBe('+2.50%')
    expect(formatPct('-1.5')).toBe('-1.50%')
  })

  it('returns dash for null', () => {
    expect(formatPct(null)).toBe('—')
  })

  it('returns dash for undefined', () => {
    expect(formatPct(undefined)).toBe('—')
  })

  it('returns dash for NaN', () => {
    expect(formatPct('abc')).toBe('—')
  })
})

describe('formatCompact', () => {
  it('formats billions', () => {
    expect(formatCompact(1500000000)).toBe('1.5B')
    expect(formatCompact(2000000000)).toBe('2.0B')
  })

  it('formats millions', () => {
    expect(formatCompact(1200000)).toBe('1.2M')
    expect(formatCompact(26600000)).toBe('26.6M')
  })

  it('formats thousands', () => {
    expect(formatCompact(5000)).toBe('5K')
    expect(formatCompact(12500)).toBe('13K')  // rounds
  })

  it('formats small numbers', () => {
    expect(formatCompact(500)).toBe('500')
    expect(formatCompact(0)).toBe('0')
  })

  it('formats negative billions', () => {
    expect(formatCompact(-1500000000)).toBe('-1.5B')
  })

  it('formats negative millions', () => {
    expect(formatCompact(-1200000)).toBe('-1.2M')
  })

  it('formats negative thousands', () => {
    expect(formatCompact(-5000)).toBe('-5K')
  })

  it('handles string input', () => {
    expect(formatCompact('1000000')).toBe('1.0M')
  })

  it('returns dash for null', () => {
    expect(formatCompact(null)).toBe('—')
  })

  it('returns dash for undefined', () => {
    expect(formatCompact(undefined)).toBe('—')
  })

  it('returns dash for NaN', () => {
    expect(formatCompact('abc')).toBe('—')
  })
})
