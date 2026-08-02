export interface ChatConversation {
  id: string
  title: string
  model_id: string
  thinking_effort: string
  created_at: string
  updated_at: string
}

export interface ChatMessageRow {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: unknown // JSONB — Vercel AI SDK UIMessage content format
  created_at: string
}
