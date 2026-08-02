import { useState } from 'react'
import { ChevronDown, ChevronRight, Pencil, LogOut } from 'lucide-react'
import { Button } from '../ui/button'
import { cn, formatPct, formatCompact, formatSignedCompact, plColor } from '../../lib/utils'
import { formatMinDate } from '../../lib/date'
import { STRATEGY_BADGE_COLOR } from '../../lib/strategy'
import { computeUnrealizedPl } from '../../lib/trade-grouping'
import type { TickerTradeGroup } from '../../lib/trade-grouping'
import type { Trade } from '../../types/index'

interface TickerPositionCardProps {
  group: TickerTradeGroup
  currentPriceVnd?: number | null
  onEditTrade: (trade: Trade) => void
  onCloseTrade: (trade: Trade) => void
}

export function TickerPositionCard({
  group,
  currentPriceVnd,
  onEditTrade,
  onCloseTrade,
}: TickerPositionCardProps) {
  const [expanded, setExpanded] = useState(group.openTrades.length > 1)

  const { unrealizedPlVnd, unrealizedPlPct } = computeUnrealizedPl(
    currentPriceVnd,
    group.avgEntryPriceVnd,
    group.totalOpenShares
  )

  const hasMultipleLots = group.openTrades.length > 1

  return (
    <div className="rounded-lg border bg-card transition-colors hover:bg-accent/5">
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'flex w-full items-center gap-4 px-4 py-3 text-left cursor-pointer',
          hasMultipleLots && 'hover:bg-accent/10'
        )}
      >
        {hasMultipleLots ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )
        ) : (
          <div className="h-4 w-4 shrink-0" />
        )}

        <span className="text-base font-semibold w-16">{group.ticker}</span>

        <span className="text-sm text-muted-foreground">
          {group.totalOpenShares.toLocaleString('vi-VN')} shares
        </span>

        <span className="text-xs text-muted-foreground">
          @ {formatCompact(group.avgEntryPriceVnd)}
        </span>

        {group.strategies.length > 0 && (
          <div className="flex gap-1 ml-auto mr-4">
            {group.strategies.map((strategy) => (
              <span
                key={strategy}
                className={cn(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border',
                  STRATEGY_BADGE_COLOR[strategy] || 'bg-muted text-muted-foreground'
                )}
              >
                {strategy}
              </span>
            ))}
          </div>
        )}

        <div className="text-right ml-auto min-w-[120px]">
          {unrealizedPlVnd !== null ? (
            <div>
              <span className={cn('text-sm font-medium', plColor(unrealizedPlVnd))}>
                {formatSignedCompact(unrealizedPlVnd)}
              </span>
              {unrealizedPlPct !== null && (
                <span className={cn('text-xs ml-1.5', plColor(unrealizedPlPct))}>
                  {formatPct(unrealizedPlPct)}
                </span>
              )}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">No price data</span>
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t px-4 pb-3">
          {group.openTrades.map((trade, index) => (
            <div
              key={trade.id}
              className={cn(
                'flex items-center gap-3 py-2 text-sm',
                index > 0 && 'border-t border-dashed border-border/50'
              )}
            >
              <div className="w-4 shrink-0" />
              <span className="text-muted-foreground w-5 text-xs">
                {index === group.openTrades.length - 1 ? '└' : '├'}
              </span>
              <span className="w-20">
                {Number(trade.shares).toLocaleString('vi-VN')} sh
              </span>
              <span className="text-muted-foreground">
                @ {formatCompact(trade.entry_price_vnd)}
              </span>
              <span className="text-xs text-muted-foreground">
                {formatMinDate(trade.entry_date)}
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
              <div className="ml-auto flex gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs cursor-pointer"
                  onClick={(event) => {
                    event.stopPropagation()
                    onCloseTrade(trade)
                  }}
                >
                  <LogOut className="h-3 w-3 mr-1" />
                  Close
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs cursor-pointer"
                  onClick={(event) => {
                    event.stopPropagation()
                    onEditTrade(trade)
                  }}
                >
                  <Pencil className="h-3 w-3 mr-1" />
                  Edit
                </Button>
              </div>
            </div>
          ))}

          {group.closedTrades.length > 0 && (
            <div className="mt-2 pt-2 border-t border-border/50">
              <span className="text-xs text-muted-foreground">
                {group.closedTrades.length} closed trade{group.closedTrades.length > 1 ? 's' : ''} ·{' '}
                {group.wins}W/{group.losses}L ·{' '}
                <span className={plColor(group.netPlVnd)}>
                  {formatSignedCompact(group.netPlVnd)} realized
                </span>
              </span>
            </div>
          )}
        </div>
      )}

      {!hasMultipleLots && group.openTrades.length === 1 && !expanded && (
        <div className="flex items-center gap-1 border-t px-4 py-2">
          <span className="text-xs text-muted-foreground mr-auto">
            Entered {formatMinDate(group.openTrades[0].entry_date)}
            {group.closedTrades.length > 0 && (
              <> · {group.wins}W/{group.losses}L history</>
            )}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs cursor-pointer"
            onClick={() => onCloseTrade(group.openTrades[0])}
          >
            <LogOut className="h-3 w-3 mr-1" />
            Close
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs cursor-pointer"
            onClick={() => onEditTrade(group.openTrades[0])}
          >
            <Pencil className="h-3 w-3 mr-1" />
            Edit
          </Button>
        </div>
      )}
    </div>
  )
}
