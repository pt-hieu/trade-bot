/**
 * User-facing strip for data-layer audit provenance tags.
 *
 * Mirrors `scripts/shared/rules/audit_tags.py`. Pipeline writes these tags
 * into `daily_recommendations.rationale` + `.verdict` so reviewers can
 * trace which reconciliation path produced a row; the strip runs at the
 * web read boundary so users see substantive prose only. DB audit trail
 * stays intact.
 */

const AUDIT_TAGS = [
  '[DERIVED_FROM_BELIEFS]',
  '[RECONCILED_FROM_BELIEFS]',
  '[NO_BELIEF_NO_REC]',
] as const

const TAG_PATTERN = new RegExp(
  '\\s*(?:' + AUDIT_TAGS.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\s*',
  'g',
)

export function stripAuditTags(text: string | null | undefined): string | null {
  if (!text) return text ?? null
  const cleaned = text.replace(TAG_PATTERN, ' ').replace(/\s{2,}/g, ' ').trim()
  return cleaned.length > 0 ? cleaned : null
}
