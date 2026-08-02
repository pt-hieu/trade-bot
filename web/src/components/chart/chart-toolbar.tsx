import { cn } from '../../lib/utils'
import type { ChartInterval } from '../../types/chart'

const INTERVALS: { label: string; value: ChartInterval }[] = [
  { label: '1D', value: '1D' },
  { label: '1H', value: '1H' },
  { label: '15m', value: '15m' },
]

interface ChartToolbarProps {
  interval: ChartInterval
  onIntervalChange: (interval: ChartInterval) => void
  showSma20: boolean
  showSma50: boolean
  onToggleSma20: () => void
  onToggleSma50: () => void
  isConnected?: boolean
  ticker?: string
}

export function ChartToolbar({
  interval,
  onIntervalChange,
  showSma20,
  showSma50,
  onToggleSma20,
  onToggleSma50,
  isConnected,
  ticker,
}: ChartToolbarProps) {
  return (
    <div className="flex items-center justify-between px-1 pb-2">
      <div className="flex items-center gap-1">
        {/* Interval pills */}
        <div className="flex items-center gap-0.5 mr-2">
          {INTERVALS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => onIntervalChange(value)}
              className={cn(
                'px-2 py-0.5 rounded text-[10px] font-mono font-medium transition-colors',
                interval === value
                  ? 'bg-zinc-700 text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              data-test-id={`chart-interval-${value}`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="w-px h-3 bg-border/50 mr-2" />

        {/* Overlay toggles */}
        <button
          onClick={onToggleSma20}
          className={cn(
            'px-2 py-0.5 rounded text-[10px] font-mono transition-colors',
            showSma20
              ? 'text-amber-400 bg-amber-500/10'
              : 'text-muted-foreground hover:text-foreground'
          )}
          data-test-id="chart-toggle-sma20"
        >
          SMA 20
        </button>
        <button
          onClick={onToggleSma50}
          className={cn(
            'px-2 py-0.5 rounded text-[10px] font-mono transition-colors',
            showSma50
              ? 'text-blue-400 bg-blue-500/10'
              : 'text-muted-foreground hover:text-foreground'
          )}
          data-test-id="chart-toggle-sma50"
        >
          SMA 50
        </button>
      </div>

      {/* Live indicator */}
      {isConnected && ticker && (
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[10px] text-emerald-500 font-mono">LIVE</span>
        </div>
      )}
    </div>
  )
}
