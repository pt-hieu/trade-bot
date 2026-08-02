import { useState } from 'react'
import { ChevronDown, ChevronRight, Pencil, Trash2 } from 'lucide-react'
import { Button } from '../ui/button'
import { PlBar } from './pl-bar'
import { cn, formatPct, formatCompact, formatSignedCompact, plColor } from '../../lib/utils'
import { formatMinDate } from '../../lib/date'
import { STRATEGY_BADGE_COLOR } from '../../lib/strategy'
import type { TickerTradeGroup } from '../../lib/trade-grouping'
import type { Trade } from '../../types/index'

interface TickerHistoryRowProps {
  group: TickerTradeGroup
  maxAbsolutePlVnd: number
  onEditTrade: (trade: Trade) => void
  onDeleteTrade: (trade: Trade) => void
}

export function TickerHistoryRow({
  group,
  maxAbsolutePlVnd,
  onEditTrade,
  onDeleteTrade,
}: TickerHistoryRowProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-lg border bg-card/50 opacity-75 hover:opacity-100 transition-opacity">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-4 px-4 py-2.5 text-left cursor-pointer"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}

        <span className="text-sm font-semibold w-14">{group.ticker}</span>

        <span className="text-xs text-muted-foreground w-16">
          {group.tradeCount} trade{group.tradeCount > 1 ? 's' : ''}
        </span>

        <span className="text-xs w-12">
          <span className="text-emerald-400">{group.wins}W</span>
          <span className="text-muted-foreground">/</span>
          <span className="text-rose-400">{group.losses}L</span>
        </span>

        <div className="flex-1 max-w-[200px]">
          <PlBar valueVnd={group.netPlVnd} maxAbsoluteVnd={maxAbsolutePlVnd} showLabel />
        </div>

        <div className="text-right min-w-[100px]">
          <span className={cn('text-sm font-medium', plColor(group.netPlVnd))}>
            {formatSignedCompact(group.netPlVnd)}
          </span>
          {group.netPlPct !== null && (
            <span className={cn('text-xs ml-1.5', plColor(group.netPlPct))}>
              {formatPct(group.netPlPct)}
            </span>
          )}
        </div>
      </button>

      {/* Expanded: individual closed trades */}
      {expanded && (
        <div className="border-t px-4 pb-2">
          {group.closedTrades.map((trade) => (
            <div
              key={trade.id}
              className="flex items-center gap-3 py-2 text-xs border-b border-dashed border-border/30 last:border-0"
            >
              <div className="w-3.5 shrink-0" />
              <span className="w-16 text-muted-foreground">
                {formatMinDate(trade.entry_date)}
              </span>
              <span className="text-muted-foreground">→</span>
              <span className="w-16 text-muted-foreground">
                {trade.exit_date ? formatMinDate(trade.exit_date) : '—'}
              </span>
              <span className="w-14">
                {Number(trade.shares).toLocaleString('vi-VN')} sh
              </span>
              <span className="text-muted-foreground">
                {formatCompact(trade.entry_price_vnd)} → {trade.exit_price_vnd ? formatCompact(trade.exit_price_vnd) : '—'}
              </span>
              {trade.strategy && (
                <span
                  className={cn(
                    'inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium border',
                    STRATEGY_BADGE_COLOR[trade.strategy] || 'bg-muted text-muted-foreground'
                  )}
                >
                  {trade.strategy}
                </span>
              )}
              <span className={cn('ml-auto font-medium', plColor(trade.pl_net_vnd))}>
                {trade.pl_net_vnd != null ? formatSignedCompact(trade.pl_net_vnd) : '—'}
              </span>
              <span className={cn('w-14 text-right', plColor(trade.pl_pct))}>
                {trade.pl_pct != null ? formatPct(trade.pl_pct) : '—'}
              </span>
              <div className="flex gap-0.5">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 cursor-pointer"
                  onClick={(event) => {
                    event.stopPropagation()
                    onEditTrade(trade)
                  }}
                >
                  <Pencil className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 text-destructive hover:text-destructive cursor-pointer"
                  onClick={(event) => {
                    event.stopPropagation()
                    onDeleteTrade(trade)
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
