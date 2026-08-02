import { cn, formatCompact, formatPct, formatSignedCompact, formatWinRate, plColor } from '../../lib/utils'
import { computeUnrealizedPl } from '../../lib/trade-grouping'
import type { TickerTradeGroup } from '../../lib/trade-grouping'

interface TickerContextCardProps {
  group: TickerTradeGroup
  currentPrice: number | null
}

export function TickerContextCard({ group, currentPrice }: TickerContextCardProps) {
  const hasOpenPosition = group.openTrades.length > 0
  const { unrealizedPlVnd, unrealizedPlPct } = computeUnrealizedPl(
    currentPrice,
    group.avgEntryPriceVnd,
    group.totalOpenShares
  )

  return (
    <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
      {hasOpenPosition ? (
        <div>
          <p className="text-sm font-medium">
            You hold{' '}
            <span className="text-foreground">
              {group.totalOpenShares.toLocaleString('vi-VN')} shares
            </span>{' '}
            @ {formatCompact(group.avgEntryPriceVnd)}
          </p>
          {unrealizedPlVnd !== null && (
            <p className={cn('text-sm font-semibold', plColor(unrealizedPlVnd))}>
              {formatSignedCompact(unrealizedPlVnd)}{' '}
              ({formatPct(unrealizedPlPct)})
              <span className="font-normal text-muted-foreground ml-1.5">
                unrealized
              </span>
            </p>
          )}
          {currentPrice && group.avgEntryPriceVnd > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Current price{' '}
              <span
                className={cn(
                  'font-medium',
                  currentPrice >= group.avgEntryPriceVnd
                    ? 'text-emerald-400'
                    : 'text-rose-400'
                )}
              >
                {formatCompact(currentPrice)}
              </span>
              {currentPrice < group.avgEntryPriceVnd
                ? ' — below your avg entry'
                : ' — above your avg entry'}
            </p>
          )}
        </div>
      ) : currentPrice ? (
        <p className="text-sm">
          <span className="text-muted-foreground">Current price</span>{' '}
          <span className="font-medium">{formatCompact(currentPrice)}</span>
        </p>
      ) : null}

      {group.closedTrades.length > 0 && (
        <div className="flex items-center gap-3 text-xs pt-1 border-t border-border/40">
          <span className="text-muted-foreground">
            {group.closedTrades.length} past trade{group.closedTrades.length > 1 ? 's' : ''}
          </span>
          <span>
            <span className="text-emerald-400">{group.wins}W</span>
            <span className="text-muted-foreground">/</span>
            <span className="text-rose-400">{group.losses}L</span>
          </span>
          {group.winRate !== null && (
            <span className="text-muted-foreground">
              {formatWinRate(group.winRate)} win rate
            </span>
          )}
          {group.netPlVnd !== 0 && (
            <span className={cn('font-medium', plColor(group.netPlVnd))}>
              {formatSignedCompact(group.netPlVnd)} realized
            </span>
          )}
        </div>
      )}
    </div>
  )
}
