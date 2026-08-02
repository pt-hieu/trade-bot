import { useState } from 'react'
import { LogOut, Plus, Sparkles } from 'lucide-react'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { Badge } from '../ui/badge'
import { Tooltip, TooltipTrigger, TooltipContent } from '../ui/tooltip'
import { PanelHeader, PanelError } from './panel'
import { Button } from '../ui/button'
import { cn, formatVND } from '../../lib/utils'
import { formatShortDate } from '../../lib/date'
import { useTrades } from '../../hooks/use-trades'
import { useScanDates, useRecommendations } from '../../hooks/use-intel'
import { ACTION_COLORS } from '../briefing/recommendations/shared'
import { TradeDialog } from '../trade-dialog'
import { STRATEGY_BORDER_COLOR, STRATEGY_BADGE_COLOR, STRATEGY_DEFINITIONS } from '../../lib/strategy'
import type { Strategy } from '../../lib/strategy'
import type { Trade, Recommendation } from '../../types/index'

function TradeRow({ trade, onTickerClick, onClose }: { trade: Trade; onTickerClick?: (ticker: string) => void; onClose?: (trade: Trade) => void }) {
  const borderClass = trade.strategy ? STRATEGY_BORDER_COLOR[trade.strategy] : 'border-l-muted'
  const badgeClass = trade.strategy ? STRATEGY_BADGE_COLOR[trade.strategy] : ''
  const definition = trade.strategy ? STRATEGY_DEFINITIONS[trade.strategy as Strategy] : undefined

  return (
    <div
      className={cn('flex items-center gap-3 px-4 py-2 border-l-2 cursor-pointer hover:bg-muted/20 transition-colors', borderClass)}
      onClick={() => onTickerClick?.(trade.ticker)}
      data-test-id={`open-trade-${trade.id}`}
    >
      <span
        className="font-mono font-semibold text-sm w-12 shrink-0 text-left"
        data-test-id={`trade-ticker-${trade.ticker}`}
      >
        {trade.ticker}
      </span>
      {trade.strategy && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge className={cn('text-[10px] px-1.5 py-0 h-4 shrink-0', badgeClass)}>
              {trade.strategy}
            </Badge>
          </TooltipTrigger>
          {definition && (
            <TooltipContent side="top" className="max-w-[240px]">
              {definition}
            </TooltipContent>
          )}
        </Tooltip>
      )}
      <span className="text-[10px] text-muted-foreground shrink-0">
        {formatShortDate(trade.entry_date)}
      </span>
      {trade.days_held != null && (
        <span className="text-[10px] text-muted-foreground font-mono tabular-nums shrink-0">
          {trade.days_held}d
        </span>
      )}
      <span className="text-[10px] text-muted-foreground font-mono tabular-nums ml-auto shrink-0">
        {formatVND(trade.entry_price_vnd)}
      </span>
      <Button
        variant="ghost"
        size="icon-xs"
        className="shrink-0 text-muted-foreground hover:text-rose-400 h-5 w-5"
        onClick={(e) => { e.stopPropagation(); onClose?.(trade) }}
        title="Close trade"
        data-test-id={`close-trade-${trade.id}`}
      >
        <LogOut className="h-3 w-3" />
      </Button>
    </div>
  )
}

function PickRow({ rec, onTickerClick }: { rec: Recommendation; onTickerClick?: (ticker: string) => void }) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-2 cursor-pointer hover:bg-muted/20 transition-colors"
      onClick={() => onTickerClick?.(rec.ticker)}
      data-test-id={`top-pick-${rec.ticker}`}
    >
      <Sparkles className="h-3 w-3 text-amber-400 shrink-0" />
      <span className="font-mono font-semibold text-sm w-12 shrink-0">{rec.ticker}</span>
      <Badge className={cn('text-[10px] px-1.5 py-0 h-4 shrink-0 font-mono', ACTION_COLORS[rec.action])}>
        {rec.action.replace('_', ' ')}
      </Badge>
      {rec.entry_price_vnd && (
        <span className="text-[10px] text-muted-foreground font-mono tabular-nums shrink-0">
          E {formatVND(rec.entry_price_vnd)}
        </span>
      )}
      {rec.stop_price_vnd && (
        <span className="text-[10px] text-rose-400/70 font-mono tabular-nums shrink-0">
          S {formatVND(rec.stop_price_vnd)}
        </span>
      )}
      {rec.target_price_vnd && (
        <span className="text-[10px] text-emerald-400/70 font-mono tabular-nums shrink-0">
          T {formatVND(rec.target_price_vnd)}
        </span>
      )}
      {rec.rationale && (
        <span className="text-[10px] text-muted-foreground truncate flex-1 min-w-0">
          {rec.rationale}
        </span>
      )}
    </div>
  )
}

interface OpenTradesPanelProps {
  onTickerClick?: (ticker: string) => void
}

export function OpenTradesPanel({ onTickerClick }: OpenTradesPanelProps) {
  const { data: allTrades, isLoading, error, refetch } = useTrades()
  const [newTradeOpen, setNewTradeOpen] = useState(false)
  const [closeTrade, setCloseTrade] = useState<Trade | null>(null)

  const { data: scanDates } = useScanDates()
  const { data: recs } = useRecommendations(scanDates?.[0])
  const topPicks = recs?.recommendations.filter((r) => r.section === 'TOP_PICKS') ?? []

  const openTrades = allTrades?.filter((t) => t.status === 'OPEN') ?? []

  return (
    <Card className="border-border/50 py-0 gap-0 overflow-hidden">
      <PanelHeader title="Open trades" href="/trades" linkText="All trades →" count={openTrades.length}>
        <Button
          variant="ghost"
          size="icon-xs"
          className="h-5 w-5 text-muted-foreground hover:text-foreground"
          onClick={() => setNewTradeOpen(true)}
          title="New trade"
          data-test-id="new-trade-shortcut"
        >
          <Plus className="h-3 w-3" />
        </Button>
      </PanelHeader>

      <div className="divide-y divide-border/20">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2 border-l-2 border-l-muted">
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}

        {error && <PanelError message="Could not load trades" onRetry={refetch} />}

        {!isLoading && !error && openTrades.length === 0 && (
          <p className="px-4 py-4 text-xs text-muted-foreground text-center">
            No open trades
          </p>
        )}

        {!isLoading && openTrades.map((trade) => (
          <TradeRow
            key={trade.id}
            trade={trade as any}
            onTickerClick={onTickerClick}
            onClose={setCloseTrade}
          />
        ))}
      </div>

      {topPicks.length > 0 && (
        <>
          <div className="flex items-center gap-2 px-4 py-1.5 border-t border-border/30 bg-muted/10">
            <Sparkles className="h-2.5 w-2.5 text-amber-400" />
            <span className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
              Agent top picks
            </span>
          </div>
          <div className="divide-y divide-border/20">
            {topPicks.map((rec: any) => (
              <PickRow key={rec.ticker} rec={rec as any} onTickerClick={onTickerClick} />
            ))}
          </div>
        </>
      )}

      <TradeDialog
        open={newTradeOpen}
        onOpenChange={setNewTradeOpen}
      />

      <TradeDialog
        open={!!closeTrade}
        onOpenChange={(open) => { if (!open) setCloseTrade(null) }}
        trade={closeTrade ?? undefined}
        initialStatus="CLOSED"
      />
    </Card>
  )
}
