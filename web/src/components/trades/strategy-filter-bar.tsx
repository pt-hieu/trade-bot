import { X } from 'lucide-react'
import { Tooltip, TooltipTrigger, TooltipContent } from '../ui/tooltip'
import { cn } from '../../lib/utils'
import { STRATEGIES, STRATEGY_ACTIVE_COLOR, STRATEGY_DEFINITIONS } from '../../lib/strategy'
import type { Strategy } from '../../lib/strategy'

interface StrategyFilterBarProps {
  activeStrategy: Strategy | string | undefined
  onStrategyChange: (strategy: Strategy | null) => void
  strategyCounts: Map<Strategy, number>
  totalCount: number
}

export function StrategyFilterBar({
  activeStrategy,
  onStrategyChange,
  strategyCounts,
  totalCount,
}: StrategyFilterBarProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={() => onStrategyChange(null)}
        className={cn(
          'px-3 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer',
          !activeStrategy
            ? 'bg-foreground/10 text-foreground border-foreground/20'
            : 'text-muted-foreground border-border/40 hover:border-border hover:text-foreground'
        )}
      >
        All
        <span className="ml-1 text-muted-foreground">{totalCount}</span>
      </button>
      {STRATEGIES.map((strategy) => {
        const count = strategyCounts.get(strategy) || 0
        return (
          <Tooltip key={strategy}>
            <TooltipTrigger asChild>
              <button
                onClick={() =>
                  onStrategyChange(activeStrategy === strategy ? null : strategy)
                }
                className={cn(
                  'flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer',
                  activeStrategy === strategy
                    ? STRATEGY_ACTIVE_COLOR[strategy]
                    : 'text-muted-foreground border-border/40 hover:border-border hover:text-foreground',
                  count === 0 && 'opacity-40'
                )}
              >
                {strategy}
                <span className="text-[10px] opacity-70">{count}</span>
                {activeStrategy === strategy && <X className="h-2.5 w-2.5" />}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[240px]">
              {STRATEGY_DEFINITIONS[strategy]}
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}
