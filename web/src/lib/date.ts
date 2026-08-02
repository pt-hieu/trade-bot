import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(utc)
dayjs.extend(relativeTime)

/** Parse a YYYY-MM-DD string as a local date (no timezone shift).
 *  Uses T12:00:00 (noon) to avoid date shift in any timezone. */
export function parseDate(dateStr: string | Date | unknown) {
  const str = toDateStr(dateStr)
  return dayjs(str + 'T12:00:00')
}

/** Format as "Mon, 09 Feb 2026" */
export function formatDisplayDate(dateStr: string): string {
  return parseDate(dateStr).format('ddd, DD MMM YYYY')
}

/** Format as "09 Feb 2026" */
export function formatShortDate(dateStr: string): string {
  return parseDate(dateStr).format('DD MMM YYYY')
}

/** Format as "09 Feb" */
export function formatMinDate(dateStr: string): string {
  return parseDate(dateStr).format('DD MMM')
}

/** Relative time: "2 hours ago", "3 days ago" */
export function formatRelativeTime(dateStr: string): string {
  return dayjs(dateStr).fromNow()
}

/** Format a date string or Date object for HTML date input (YYYY-MM-DD) */
export function formatDateForInput(date: string | Date | null | undefined): string {
  if (!date) return ''
  if (date instanceof Date) return date.toISOString().split('T')[0]
  return date.split('T')[0]
}

/** Normalize any date value to YYYY-MM-DD string (for API routes).
 *  Neon returns DATE columns as JS Date at midnight local time,
 *  so we use dayjs local (not .utc()) to avoid timezone date shift. */
export function toDateStr(val: unknown): string {
  if (typeof val === 'string') return val.slice(0, 10)
  if (val instanceof Date) return dayjs(val).format('YYYY-MM-DD')
  const d = dayjs(String(val))
  if (d.isValid()) return d.format('YYYY-MM-DD')
  return String(val).slice(0, 10)
}
