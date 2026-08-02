/**
 * OpenRouter models available for chat — all support function calling.
 * Mirrors the model options pattern from web/lib/models.ts.
 */
export const CHAT_MODELS = [
  { id: 'moonshotai/Kimi-K2.5', label: 'Kimi K2.5', supportsThinking: true, contextWindow: 262_144 },
  { id: 'Qwen/Qwen3.5-397B-A17B', label: 'Qwen 3.5', supportsThinking: true, contextWindow: 262_144 },
  { id: 'minimax/minimax-m2.7', label: 'MiniMax M2.7', supportsThinking: true, contextWindow: 228_700 },
] as const

export type ThinkingEffort = 'off' | 'low' | 'high'

export type ChatModelId = (typeof CHAT_MODELS)[number]['id']

export const DEFAULT_CHAT_MODEL: ChatModelId = 'moonshotai/Kimi-K2.5'

export function getChatModelLabel(id: string): string {
  return CHAT_MODELS.find((m) => m.id === id)?.label ?? id.split('/').pop() ?? id
}

export function isValidChatModel(id: string): id is ChatModelId {
  return CHAT_MODELS.some((m) => m.id === id)
}

export function modelSupportsThinking(id: string): boolean {
  return CHAT_MODELS.find((m) => m.id === id)?.supportsThinking ?? false
}

export function getContextWindow(id: string): number {
  return CHAT_MODELS.find((m) => m.id === id)?.contextWindow ?? 262_144
}

// ─── Sub-agent model routing ─────────────────────────────────────────────────

export type SubAgentModelKey = 'heavy' | 'light'

export const SUB_AGENT_MODELS: Record<SubAgentModelKey, string> = {
  heavy: 'moonshotai/Kimi-K2.5',
  light: 'minimax/minimax-m2.7',
}

