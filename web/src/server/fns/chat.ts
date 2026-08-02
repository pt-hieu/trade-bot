import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'

export const getConversations = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT id, title, model_id, created_at, updated_at
    FROM chat_conversations
    ORDER BY updated_at DESC
    LIMIT 30
  `
  return rows
})

export const deleteConversation = createServerFn({ method: 'POST' })
  .inputValidator((data: { id: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    await sql`DELETE FROM chat_conversations WHERE id = ${data.id}`
    return { deleted: true }
  })

export const getConversation = createServerFn({ method: 'GET' })
  .inputValidator((data: { id: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()

    const [convRows, msgRows] = await Promise.all([
      sql`SELECT id, title, model_id, thinking_effort, created_at, updated_at FROM chat_conversations WHERE id = ${data.id}`,
      sql`
        SELECT id, role, content, created_at
        FROM chat_messages
        WHERE conversation_id = ${data.id}
        ORDER BY created_at ASC
      `,
    ])

    if (!convRows.length) throw new Error('Conversation not found')

    return { conversation: convRows[0], messages: msgRows }
  })
