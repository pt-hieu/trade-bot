import { useState } from 'react'
import { ChevronDown, Zap, Brain, BrainCircuit, Minus } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { CHAT_MODELS, getChatModelLabel, type ChatModelId, type ThinkingEffort } from '../../lib/chat/models'
import { cn } from '../../lib/utils'
import type { UsageData } from '../../lib/chat/data-parts'

interface ChatSettingsProps {
  model: ChatModelId
  onModelChange: (model: ChatModelId) => void
  thinking: ThinkingEffort
  onThinkingChange: (effort: ThinkingEffort) => void
  supportsThinking: boolean
  disabled?: boolean
  usage?: UsageData | null
  className?: string
}

function formatK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

function UsageIndicator({ usage }: { usage: UsageData }) {
  const pct = Math.min(100, Math.round((usage.inputTokens / usage.contextWindow) * 100))
  const remaining = Math.max(0, usage.contextWindow - usage.inputTokens)

  const barColor =
    pct >= 80
      ? 'bg-red-500/70'
      : pct >= 50
        ? 'bg-amber-500/70'
        : 'bg-emerald-500/60'

  const textColor =
    pct >= 80
      ? 'text-red-400/70'
      : pct >= 50
        ? 'text-amber-400/70'
        : 'text-muted-foreground/50'

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className="flex items-center gap-1.5 cursor-help"
          data-test-id="chat-usage-indicator"
        >
          <span className={cn('text-[10px] font-mono tabular-nums', textColor)}>
            {formatK(usage.inputTokens)}↑
          </span>
          <div className="w-10 h-1 rounded-full bg-muted/20 overflow-hidden flex-shrink-0">
            <div
              className={cn('h-full rounded-full transition-all duration-500', barColor)}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className={cn('text-[9px] font-mono tabular-nums', textColor)}>
            {pct}%
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="top" className="bg-zinc-900 text-[11px] font-mono space-y-0.5 border border-border/40">
        <div className="text-foreground/80">Context usage</div>
        <div className="text-muted-foreground">in: {usage.inputTokens.toLocaleString()} tokens</div>
        <div className="text-muted-foreground">out: {usage.outputTokens.toLocaleString()} tokens</div>
        <div className="text-muted-foreground">remaining: {remaining.toLocaleString()} tokens</div>
        <div className="text-muted-foreground/50">window: {usage.contextWindow.toLocaleString()}</div>
      </TooltipContent>
    </Tooltip>
  )
}

const THINKING_LEVELS: { value: ThinkingEffort; Icon: LucideIcon; label: string }[] = [
  { value: 'off', Icon: Minus, label: 'off' },
  { value: 'low', Icon: Brain, label: 'low' },
  { value: 'high', Icon: BrainCircuit, label: 'high' },
]

function ThinkingIcon({ effort }: { effort: ThinkingEffort }) {
  const level = THINKING_LEVELS.find((l) => l.value === effort)!
  return <level.Icon className="h-2.5 w-2.5" />
}

export function ChatSettings({
  model,
  onModelChange,
  thinking,
  onThinkingChange,
  supportsThinking,
  disabled,
  usage,
  className,
}: ChatSettingsProps) {
  const [open, setOpen] = useState(false)
  const label = getChatModelLabel(model)

  return (
    <div
      className={cn(
        'flex items-center gap-2.5 px-3 py-1.5 border-t border-border/30 transition-opacity',
        disabled && 'opacity-60',
        className,
      )}
    >
      {/* Model picker */}
      {disabled ? (
        <span className="text-[11px] font-mono text-muted-foreground/60 tracking-wide">
          {label}
        </span>
      ) : (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground/70 hover:text-foreground/80 transition-colors cursor-pointer group"
              data-test-id="chat-model-trigger"
            >
              {label}
              <ChevronDown className="h-2.5 w-2.5 text-muted-foreground/40 group-hover:text-muted-foreground/70 transition-colors" />
            </button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            side="top"
            sideOffset={6}
            className="p-1 w-48 border-border/50 bg-background/95 backdrop-blur-sm"
          >
            {CHAT_MODELS.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  onModelChange(m.id)
                  setOpen(false)
                }}
                className={cn(
                  'w-full flex items-center justify-between px-2 py-1.5 rounded-sm text-[11px] font-mono transition-colors cursor-pointer',
                  m.id === model
                    ? 'bg-primary/10 text-foreground/90 border-l-2 border-primary/60'
                    : 'text-muted-foreground/60 hover:bg-muted/30 hover:text-foreground/80 border-l-2 border-transparent',
                )}
                data-test-id={`chat-model-option-${m.label.toLowerCase().replace(/\s+/g, '-')}`}
              >
                <span>{m.label}</span>
                {m.supportsThinking && (
                  <Zap className="h-2.5 w-2.5 text-amber-500/50 flex-shrink-0" />
                )}
              </button>
            ))}
          </PopoverContent>
        </Popover>
      )}

      {/* Thinking section */}
      {supportsThinking && (
        <>
          <span className="text-[10px] font-mono text-border/50 select-none">·</span>
          {disabled ? (
            <span className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground/40 tracking-wide">
              think:{' '}
              <span className="flex items-center gap-0.5 text-amber-500/50">
                <ThinkingIcon effort={thinking} />
                {thinking}
              </span>
            </span>
          ) : (
            <div className="flex items-center rounded border border-border/30 overflow-hidden flex-shrink-0">
              {THINKING_LEVELS.map(({ value, Icon, label }) => (
                <button
                  key={value}
                  onClick={() => onThinkingChange(value)}
                  className={cn(
                    'flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-mono tracking-wide transition-colors cursor-pointer',
                    thinking === value
                      ? 'bg-amber-500/15 text-amber-400/80'
                      : 'text-muted-foreground/40 hover:text-muted-foreground/70 hover:bg-muted/20',
                  )}
                  data-test-id={`thinking-${value}`}
                >
                  <Icon className="h-2.5 w-2.5" />
                  {label}
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {/* Context usage — rightmost */}
      {usage && (
        <>
          <span className="ml-auto" />
          <UsageIndicator usage={usage} />
        </>
      )}
    </div>
  )
}
