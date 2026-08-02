import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatVND(amount: number | string | null | undefined): string {
  if (amount == null) return '—'
  const num = Number(amount)
  if (isNaN(num)) return '—'
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
  }).format(num)
}

export function formatPct(pct: number | string | null | undefined, decimals = 2): string {
  if (pct == null) return '—'
  const num = Number(pct)
  if (isNaN(num)) return '—'
  const formatted = num.toFixed(decimals)
  return num >= 0 ? `+${formatted}%` : `${formatted}%`
}

/** Format a 0-1 decimal as a whole-number percentage (e.g. 0.65 → "65%") */
export function formatWinRate(decimal: number | string | null | undefined): string {
  if (decimal == null) return '—'
  const num = Number(decimal)
  if (isNaN(num)) return '—'
  return `${(num * 100).toFixed(0)}%`
}

/** Accuracy color class for 0-1 ratios — emerald ≥0.6, amber ≥0.4, rose below */
export function accuracyColor(value: number | null, thresholds?: { high?: number; mid?: number }): string {
  const num = Number(value ?? 0)
  const high = thresholds?.high ?? 0.60
  const mid = thresholds?.mid ?? 0.40
  return num >= high ? 'text-emerald-400' : num >= mid ? 'text-amber-400' : 'text-rose-400'
}

/** P/L color class — emerald for positive, rose for negative */
export function plColor(value: number | string | null | undefined): string {
  if (value == null) return 'text-muted-foreground'
  const num = Number(value)
  if (isNaN(num) || num === 0) return 'text-muted-foreground'
  return num > 0 ? 'text-emerald-500' : 'text-rose-500'
}

/** Format price in thousands (VND → K display, e.g. 26600000 → "26.600") */
export function formatVNDK(vnd: number | string | null | undefined): string {
  if (vnd == null) return '—'
  const num = Number(vnd)
  if (isNaN(num)) return '—'
  return Math.round(num / 1000).toLocaleString('vi-VN')
}

export function toTitleCase(str: string | null | undefined): string {
  if (!str) return '—'
  return str
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatCompact(value: number | string | null | undefined): string {
  if (value == null) return '—'
  const num = Number(value)
  if (isNaN(num)) return '—'
  const abs = Math.abs(num)
  const sign = num < 0 ? '-' : ''
  if (abs >= 1_000_000_000) return `${sign}${(abs / 1_000_000_000).toFixed(1)}B`
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(0)}K`
  return num.toFixed(0)
}

/** Format compact with explicit +/- sign (e.g. "+1.5M", "-200K") */
export function formatSignedCompact(value: number | string | null | undefined): string {
  if (value == null) return '—'
  const num = Number(value)
  if (isNaN(num)) return '—'
  const prefix = num >= 0 ? '+' : ''
  return `${prefix}${formatCompact(num)}`
}
