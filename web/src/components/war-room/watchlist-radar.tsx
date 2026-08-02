import { Pin } from 'lucide-react'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { PanelHeader, PanelError } from './panel'
import { Badge } from '../ui/badge'
import { cn, toTitleCase } from '../../lib/utils'
import { classifyRsi } from '../../lib/rsi'
import { useSwingWatchlist } from '../../hooks/use-watchlist'
import { useSparklineData } from '../../hooks/use-sparkline-data'
import { Sparkline } from '../ui/sparkline'
import type { SwingWatchlistItem } from '../../types/index'

function WatchlistRow({
  item,
  sparkData,
  onTickerClick,
}: {
  item: SwingWatchlistItem
  sparkData?: { close: number }[]
  onTickerClick?: (ticker: string) => void
}) {
  const rsi = classifyRsi(item.rsi)
  const rsiValue = item.rsi != null ? Number(item.rsi).toFixed(1) : '—'

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/20 transition-colors"
      onClick={() => onTickerClick?.(item.ticker)}
      data-test-id={`watchlist-radar-${item.ticker}`}
    >
      <span
        className="font-mono font-semibold text-sm w-12 shrink-0 text-left"
        data-test-id={`watchlist-ticker-${item.ticker}`}
      >
        {item.ticker}
      </span>
      <Badge className={cn('text-[10px] px-1.5 py-0 h-4 font-mono shrink-0', rsi.badgeClass)}>
        {rsiValue}
      </Badge>
      {item.is_pinned && (
        <Pin className="h-2.5 w-2.5 text-amber-400 shrink-0" />
      )}
      <span className="text-[10px] text-muted-foreground truncate shrink-0">
        {item.sector_name ? toTitleCase(item.sector_name) : '—'}
      </span>
      <div className="flex-1 min-w-[60px]">
        {sparkData && <Sparkline data={sparkData} width="100%" height={24} />}
      </div>
    </div>
  )
}

interface WatchlistRadarProps {
  onTickerClick?: (ticker: string) => void
}

export function WatchlistRadar({ onTickerClick }: WatchlistRadarProps) {
  const { data: items, isLoading, error, refetch } = useSwingWatchlist()

  const sorted = [...(items ?? [])].sort((a, b) => (Number(a.rsi) || 999) - (Number(b.rsi) || 999))
  const actionable = sorted.filter((i) => i.rsi != null && Number(i.rsi) < 50)
  const display = actionable.length > 0 ? actionable.slice(0, 8) : sorted.slice(0, 5)
  const showFallbackNote = actionable.length === 0 && sorted.length > 0

  const { data: sparklines } = useSparklineData(display.map((i) => i.ticker))

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <PanelHeader title="Watchlist radar" href="/watchlist" linkText="Watchlist →" />

      <div className="divide-y divide-border/20">
        {isLoading &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2.5">
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-4 w-10" />
              <Skeleton className="h-3 w-20" />
            </div>
          ))}

        {error && <PanelError message="Could not load watchlist" onRetry={refetch} />}

        {!isLoading && !error && sorted.length === 0 && (
          <p className="px-4 py-4 text-xs text-muted-foreground text-center">
            No tickers on watchlist
          </p>
        )}

        {showFallbackNote && (
          <div className="px-4 py-1.5 bg-muted/10">
            <p className="text-[10px] text-muted-foreground">No tickers in buy zone — showing lowest RSI</p>
          </div>
        )}

        {!isLoading && display.map((item) => (
          <WatchlistRow
            key={item.ticker}
            item={item as any}
            sparkData={sparklines?.[item.ticker]}
            onTickerClick={onTickerClick}
          />
        ))}
      </div>
    </Card>
  )
}
