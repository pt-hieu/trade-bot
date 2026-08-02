import { neon } from '@neondatabase/serverless'

export function getSql() {
  const url = process.env.DATABASE_URL
  if (!url) {
    throw new Error('DATABASE_URL environment variable is not set')
  }
  return neon(url)
}

export function buildSetClause(
  updates: Record<string, unknown>,
  startIdx = 2
): { clause: string; values: unknown[] } {
  const keys = Object.keys(updates)
  const clause = keys.map((key, i) => `${key} = $${i + startIdx}`).join(', ')
  return { clause, values: Object.values(updates) }
}
