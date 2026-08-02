import { cn } from '../../lib/utils'
import { scoreBarColor, scoreTextColor } from './newsroom-utils'

export function ScoreIndicator({ score }: { score: number }) {
  return (
    <div className="flex flex-col items-end shrink-0 gap-1 pt-3">
      <span className={cn('font-mono text-[11px] font-semibold tabular-nums', scoreTextColor(score / 100))}>
        {score}
      </span>
      <div className="w-8 h-[3px] rounded-full bg-muted/30 overflow-hidden">
        <div
          className={cn('h-full rounded-full', scoreBarColor(score / 100))}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  )
}

export function TickerChip({ ticker, highlighted, onClick }: {
  ticker: string; highlighted?: boolean; onClick?: (ticker: string) => void
}) {
  return (
    <span
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick ? (event) => { event.stopPropagation(); onClick(ticker) } : undefined}
      className={cn(
        'font-mono text-[9px] px-1.5 py-0.5 rounded transition-colors',
        onClick && 'cursor-pointer hover:bg-blue-500/15 hover:text-blue-300',
        highlighted
          ? 'bg-blue-500/20 text-blue-300 ring-1 ring-blue-500/30'
          : 'bg-muted/30 text-muted-foreground'
      )}
    >
      {ticker}
    </span>
  )
}

export function TickerRow({ tickers, hiddenCount, highlightedTicker, onTickerClick }: {
  tickers: string[]; hiddenCount: number; highlightedTicker?: string | null; onTickerClick?: (ticker: string) => void
}) {
  return (
    <div className="flex gap-1 flex-wrap items-center">
      {tickers.map((ticker) => (
        <TickerChip key={ticker} ticker={ticker} highlighted={highlightedTicker === ticker} onClick={onTickerClick} />
      ))}
      {hiddenCount > 0 && (
        <span className="font-mono text-[9px] text-muted-foreground/50">+{hiddenCount}</span>
      )}
    </div>
  )
}

export function Dot() {
  return <span className="text-muted-foreground/20">·</span>
}

export function Section({ label, icon, children }: { label: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="text-[10px] text-muted-foreground/50">{label}</span>
      </div>
      {children}
    </div>
  )
}

export function StatBlock({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/30 bg-muted/10 px-2.5 py-1.5 space-y-0.5">
      <div className="flex items-center gap-1.5 text-muted-foreground/50">
        <Icon className="h-3 w-3" />
        <span className="text-[10px]">{label}</span>
      </div>
      <span className="text-[12px] font-mono text-foreground/80">{value}</span>
    </div>
  )
}
