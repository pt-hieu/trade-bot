import { cn, formatSignedCompact } from '../../lib/utils'

interface PlBarProps {
  valueVnd: number
  maxAbsoluteVnd: number
  showLabel?: boolean
  className?: string
}

export function PlBar({ valueVnd, maxAbsoluteVnd, showLabel = false, className }: PlBarProps) {
  const isPositive = valueVnd >= 0
  const widthPercent =
    maxAbsoluteVnd > 0 ? Math.min((Math.abs(valueVnd) / maxAbsoluteVnd) * 100, 100) : 0

  if (valueVnd === 0) return null

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="relative h-5 flex-1 rounded-sm bg-muted/30 overflow-hidden">
        <div
          className={cn(
            'absolute inset-y-0 left-0 rounded-sm transition-all duration-500',
            isPositive ? 'bg-emerald-500/25' : 'bg-rose-500/25'
          )}
          style={{ width: `${Math.max(widthPercent, 2)}%` }}
        />
        {showLabel && (
          <span
            className={cn(
              'absolute inset-y-0 flex items-center px-2 text-xs font-medium',
              isPositive ? 'text-emerald-400' : 'text-rose-400'
            )}
          >
            {formatSignedCompact(valueVnd)}
          </span>
        )}
      </div>
    </div>
  )
}
