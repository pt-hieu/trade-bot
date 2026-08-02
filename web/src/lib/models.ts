/**
 * Shared model constants and styling for agent nodes + prompt editor.
 * Single source of truth for model options, colors, and display names.
 */

export const MODEL_OPTIONS = [
  { id: 'minimax/minimax-m2.7', short: 'MiniMax-M2.7', color: 'emerald' },
  { id: 'zai-org/GLM-5', short: 'GLM-5', color: 'amber' },
  { id: 'Qwen/Qwen3.5-397B-A17B', short: 'Qwen3.5-397B', color: 'violet' },
  { id: 'moonshotai/Kimi-K2.5', short: 'Kimi-K2.5', color: 'sky' },
  { id: 'zai-org/GLM-4.7', short: 'GLM-4.7', color: 'rose' },
] as const

interface ModelStyle {
  border: string
  glow: string
  badge: string
  dot: string
}

const STYLES: Record<string, ModelStyle> = {
  emerald: {
    border: 'border-emerald-500/40',
    glow: 'shadow-emerald-500/8',
    badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    dot: 'bg-emerald-400',
  },
  amber: {
    border: 'border-amber-500/40',
    glow: 'shadow-amber-500/8',
    badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    dot: 'bg-amber-400',
  },
  violet: {
    border: 'border-violet-500/40',
    glow: 'shadow-violet-500/8',
    badge: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
    dot: 'bg-violet-400',
  },
  sky: {
    border: 'border-sky-500/40',
    glow: 'shadow-sky-500/8',
    badge: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
    dot: 'bg-sky-400',
  },
  rose: {
    border: 'border-rose-500/40',
    glow: 'shadow-rose-500/8',
    badge: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    dot: 'bg-rose-400',
  },
}

const FALLBACK_STYLE: ModelStyle = {
  border: 'border-zinc-500/40',
  glow: 'shadow-zinc-500/8',
  badge: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
  dot: 'bg-zinc-400',
}

const MODEL_COLOR_MAP = new Map<string, string>(
  MODEL_OPTIONS.map((m) => [m.id, m.color])
)

/** Get Tailwind style classes for a model ID */
export function getModelStyle(modelId: string | null): ModelStyle {
  if (!modelId) return FALLBACK_STYLE
  const color = MODEL_COLOR_MAP.get(modelId)
  return color ? STYLES[color] : FALLBACK_STYLE
}

/** Get short display name from full model ID */
export function getModelShortName(modelId: string | null): string {
  if (!modelId) return 'unknown'
  const option = MODEL_OPTIONS.find((m) => m.id === modelId)
  if (option) return option.short
  // Fallback: take last segment after /
  return modelId.split('/').pop() ?? modelId
}

// oklch edge colors matching Tailwind accent palette
const EDGE_COLORS: Record<string, string> = {
  emerald: 'oklch(0.7 0.15 160)',
  amber: 'oklch(0.75 0.15 55)',
  violet: 'oklch(0.65 0.18 290)',
  sky: 'oklch(0.7 0.14 220)',
  rose: 'oklch(0.65 0.18 10)',
}

const FALLBACK_EDGE_COLOR = 'oklch(0.5 0 0)'

/** Get oklch edge color for a model ID */
export function getModelEdgeColor(modelId: string | null): string {
  if (!modelId) return FALLBACK_EDGE_COLOR
  const color = MODEL_COLOR_MAP.get(modelId)
  return color ? EDGE_COLORS[color] : FALLBACK_EDGE_COLOR
}

/** Get dot color class for a model color key */
export function getModelDotClass(modelId: string | null): string {
  return getModelStyle(modelId).dot
}
