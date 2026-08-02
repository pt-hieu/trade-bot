/**
 * Server-side prose rendering for structured `afternoon_plan` (migration 316).
 *
 * Mirrors scripts/midday/formatter.py:format_afternoon_plan_prose so the web
 * component can keep reading a plain string without decoding JSONB.
 */

export interface AfternoonAction {
  ticker: string | null
  action: string
  confidence: string
  reason: string
}

export function formatAfternoonPlanProse(
  plan: unknown,
  note: string | null | undefined = null,
): string {
  const lines: string[] = []
  if (Array.isArray(plan)) {
    for (const raw of plan) {
      if (raw == null || typeof raw !== 'object') continue
      const entry = raw as Partial<AfternoonAction>
      const action = (entry.action ?? 'NOTE').toUpperCase()
      const confidence = (entry.confidence ?? 'LOW').toUpperCase()
      const ticker = entry.ticker ?? null
      const reasonRaw = (entry.reason ?? '').trim()
      const reason = reasonRaw.length > 0 ? reasonRaw : '(no reason provided)'
      const header = ticker ? `${action} ${ticker}` : action
      lines.push(`- ${header} [${confidence}]: ${reason}`)
    }
  }
  const noteClean = (note ?? '').trim()
  if (noteClean.length > 0) {
    if (lines.length > 0) lines.push('')
    lines.push(noteClean)
  }
  return lines.length > 0 ? lines.join('\n') : 'N/A'
}
