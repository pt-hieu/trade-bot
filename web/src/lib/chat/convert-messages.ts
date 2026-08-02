import type { UIMessage } from 'ai'
import type { ChatMessageRow } from '../../types'

/**
 * Convert DB message rows to UIMessage[] for setMessages().
 *
 * New format (array of parts): stored as JSON array — [{type, ...}, ...]
 * Legacy format (plain string): stored as JSON.stringify(text) — "\"What are my trades?\""
 *
 * Tool call parts are preserved in new format (state: 'output-available').
 */
export function convertDbMessagesToUIMessages(rows: ChatMessageRow[]): UIMessage[] {
  return rows.map((row) => {
    let parsed: unknown
    try {
      parsed = typeof row.content === 'string' ? JSON.parse(row.content) : row.content
    } catch {
      parsed = String(row.content)
    }

    // New format: array of parts
    if (Array.isArray(parsed)) {
      return { id: row.id, role: row.role, parts: parsed as UIMessage['parts'] }
    }

    // Legacy format: plain string
    const text = typeof parsed === 'string' ? parsed : JSON.stringify(parsed)
    return { id: row.id, role: row.role, parts: [{ type: 'text' as const, text }] }
  })
}
