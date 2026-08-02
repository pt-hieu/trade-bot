import { createContext, useContext, useState, type ReactNode } from 'react'
import { Sparkles } from 'lucide-react'
import { cn } from '../../lib/utils'

// ── Context ──────────────────────────────────────────────────────────────────

const InsightContext = createContext<{ on: boolean; toggle: () => void }>({
  on: false,
  toggle: () => {},
})

// ── Provider ─────────────────────────────────────────────────────────────────

interface InsightToggleProps {
  children: ReactNode
  defaultOpen?: boolean
}

export function InsightToggle({ children, defaultOpen = false }: InsightToggleProps) {
  const [on, setOn] = useState(defaultOpen)

  return (
    <InsightContext.Provider value={{ on, toggle: () => setOn((v) => !v) }}>
      {children}
    </InsightContext.Provider>
  )
}

// ── Trigger (inline, next to title) ──────────────────────────────────────────

interface InsightTriggerProps {
  className?: string
}

export function InsightTrigger({ className }: InsightTriggerProps) {
  const { on, toggle } = useContext(InsightContext)

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn('flex items-center gap-1.5 cursor-pointer group', className)}
      data-test-id="insight-toggle"
    >
      <div className={cn(
        'relative w-7 h-4 rounded-full transition-colors duration-200',
        on ? 'bg-purple-500/40' : 'bg-muted'
      )}>
        <div className={cn(
          'absolute top-0.5 w-3 h-3 rounded-full transition-all duration-200',
          on
            ? 'left-3.5 bg-purple-400'
            : 'left-0.5 bg-muted-foreground/40'
        )} />
      </div>
      <Sparkles className={cn(
        'w-3 h-3 transition-colors duration-200',
        on ? 'text-purple-400' : 'text-muted-foreground/40'
      )} />
      <span className={cn(
        'text-[11px] font-medium tracking-wide transition-colors duration-200',
        on ? 'text-purple-400' : 'text-muted-foreground/40 group-hover:text-muted-foreground/60'
      )}>
        Insight
      </span>
    </button>
  )
}

// ── Card (rendered where the content should appear) ──────────────────────────

interface InsightCardProps {
  children: ReactNode
  className?: string
}

export function InsightCard({ children, className }: InsightCardProps) {
  const { on } = useContext(InsightContext)

  if (!on) return null

  return (
    <div className={cn(
      'rounded-lg border border-purple-500/15 bg-purple-500/[0.04] px-4 py-3 animate-in fade-in slide-in-from-top-1 duration-200',
      className
    )}>
      <div className="text-xs text-muted-foreground leading-relaxed">
        {children}
      </div>
    </div>
  )
}
