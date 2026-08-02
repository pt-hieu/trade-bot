import { AlertTriangle, Briefcase } from 'lucide-react'
import { Badge } from '../ui/badge'
import { InsightToggle, InsightTrigger, InsightCard } from '../ui/detail-text'
import { cn, toTitleCase } from '../../lib/utils'
import type { ForeignFlowData, FlowDetail, FlowHoldingDetail } from '../../types/index'

// ── Formatters ──────────────────────────────────────────────────────────────

function fmtB(raw: number | string | null): string {
  if (raw == null) return '—'
  const value = Number(raw)
  if (isNaN(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1) return `${value.toFixed(1)}B`
  return `${(value * 1000).toFixed(0)}M`
}

function fmtSigned(raw: number | string | null): string {
  if (raw == null) return '—'
  const value = Number(raw)
  if (isNaN(value)) return '—'
  const prefix = value >= 0 ? '+' : ''
  const abs = Math.abs(value)
  if (abs >= 1) return `${prefix}${value.toFixed(1)}B`
  return `${prefix}${(value * 1000).toFixed(0)}M`
}

// ── Buy/Sell ratio bar ──────────────────────────────────────────────────────

function RatioBar({ buyValue, sellValue }: { buyValue: number; sellValue: number }) {
  const total = buyValue + sellValue
  if (total === 0) return null
  const buyPct = (buyValue / total) * 100
  const sellPct = (sellValue / total) * 100

  return (
    <div className="space-y-1.5">
      <div className="flex h-2.5 rounded-full overflow-hidden bg-muted/30">
        <div
          className="bg-emerald-500/70 transition-all duration-500"
          style={{ width: `${buyPct}%` }}
        />
        <div
          className="bg-rose-500/70 transition-all duration-500"
          style={{ width: `${sellPct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs font-mono tabular-nums">
        <span className="text-emerald-400">Buy {fmtB(buyValue)}</span>
        <span className="text-rose-400">Sell {fmtB(sellValue)}</span>
      </div>
    </div>
  )
}

// ── Merged flow list (bought + sold, sorted by magnitude) ───────────────────

interface MergedFlowItem {
  ticker: string
  valueBillion: number
  direction: 'buy' | 'sell'
  isPortfolio: boolean
}

function mergeAndSortFlows(
  bought: FlowDetail[],
  sold: FlowDetail[],
  portfolioTickers: Set<string>,
): MergedFlowItem[] {
  const items: MergedFlowItem[] = [
    ...bought.slice(0, 5).map((detail) => ({
      ticker: detail.ticker,
      valueBillion: detail.value_billion,
      direction: 'buy' as const,
      isPortfolio: portfolioTickers.has(detail.ticker),
    })),
    ...sold.slice(0, 5).map((detail) => ({
      ticker: detail.ticker,
      valueBillion: detail.value_billion,
      direction: 'sell' as const,
      isPortfolio: portfolioTickers.has(detail.ticker),
    })),
  ]

  return items.sort((itemA, itemB) => Math.abs(itemB.valueBillion) - Math.abs(itemA.valueBillion))
}

function FlowList({ items, maxValue }: { items: MergedFlowItem[]; maxValue: number }) {
  if (items.length === 0) return null

  return (
    <div className="space-y-1">
      {items.map((item) => {
        const barWidth = maxValue > 0 ? (Math.abs(item.valueBillion) / maxValue) * 100 : 0
        const isBuy = item.direction === 'buy'

        return (
          <div key={`${item.ticker}-${item.direction}`} className="flex items-center gap-2 h-6">


            <div className="w-20 shrink-0 flex items-center gap-1.5">
              <span
                className={cn(
                  'font-mono text-xs font-medium',
                  isBuy ? 'text-emerald-400' : 'text-rose-400',
                )}
              >
                {item.ticker}
              </span>
              {item.isPortfolio && (
                <Briefcase className="h-2.5 w-2.5 text-sky-500 shrink-0" />
              )}
            </div>



            <div className="flex-1 h-3 rounded-sm overflow-hidden bg-muted/10">
              <div
                className={cn(
                  'h-full rounded-sm transition-all duration-300',
                  isBuy ? 'bg-emerald-500/50' : 'bg-rose-500/50',
                )}
                style={{ width: `${Math.max(barWidth, 3)}%` }}
              />
            </div>



            <span
              className={cn(
                'text-xs font-mono tabular-nums w-14 text-right shrink-0',
                isBuy ? 'text-emerald-400' : 'text-rose-400',
              )}
            >
              {fmtB(item.valueBillion)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Holding detail row ──────────────────────────────────────────────────────

function HoldingRow({ holding }: { holding: FlowHoldingDetail }) {
  const net = Number(holding.net_value_billion ?? 0)
  const netColor = net >= 0 ? 'text-emerald-400' : 'text-rose-400'
  const ownership = Number(holding.ownership_pct ?? 0)
  const ownershipColor = ownership >= 45 ? 'text-rose-400' : ownership >= 40 ? 'text-amber-400' : 'text-muted-foreground'

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="font-mono font-medium w-10 shrink-0">{holding.ticker}</span>
      <span className={cn('font-mono tabular-nums w-14 text-right shrink-0', netColor)}>
        {fmtSigned(net)}
      </span>
      <span className="text-zinc-500 tabular-nums font-mono text-xs w-12 text-right shrink-0">
        B {fmtB(holding.buy_value_billion)}
      </span>
      <span className="text-zinc-500 tabular-nums font-mono text-xs w-12 text-right shrink-0">
        S {fmtB(holding.sell_value_billion)}
      </span>
      {holding.ownership_pct != null && (
        <span className={cn('tabular-nums font-mono text-right shrink-0', ownershipColor)}>
          {ownership.toFixed(1)}%
        </span>
      )}
      {ownership >= 45 && <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" />}
    </div>
  )
}

// ── Main ────────────────────────────────────────────────────────────────────

interface ForeignFlowSectionProps {
  flow: ForeignFlowData
  /** Tickers from holdings/picks/watchlist for portfolio flagging */
  portfolioTickers?: Set<string>
}

export function ForeignFlowSection({ flow, portfolioTickers = new Set() }: ForeignFlowSectionProps) {
  const net = Number(flow.net_value_billion ?? 0)
  const buy = Math.abs(Number(flow.buy_value_billion ?? 0))
  const sell = Math.abs(Number(flow.sell_value_billion ?? 0))
  const isPositive = net >= 0
  const netColor = isPositive ? 'text-emerald-400' : 'text-rose-400'

  // Merged + sorted flow list
  const mergedItems = mergeAndSortFlows(flow.top_bought, flow.top_sold, portfolioTickers)
  const maxValue = mergedItems.length > 0
    ? Math.max(...mergedItems.map((item) => Math.abs(item.valueBillion)))
    : 0

  return (
    <InsightToggle>
      <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-500" style={{ animationDelay: '180ms' }}>
        {/* Header: title + signal badges */}
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Foreign Flow</h2>
          <div className="flex gap-2">
            {flow.signal && (
              <Badge variant="outline" className="text-xs font-mono">{toTitleCase(flow.signal)}</Badge>
            )}
            {flow.pattern && (
              <Badge variant="secondary" className="text-xs">{toTitleCase(flow.pattern)}</Badge>
            )}
          </div>
          {flow.interpretation && <InsightTrigger />}
        </div>

        {/* NET headline + ratio bar */}
        <div className="space-y-2">
          <p className={cn('text-2xl font-mono font-bold tabular-nums tracking-tight', netColor)}>
            {fmtSigned(net)}
          </p>
          <RatioBar buyValue={buy} sellValue={sell} />
        </div>

        {/* Merged flow list with bars */}
        {mergedItems.length > 0 && (
          <div className="pt-1">
            <FlowList items={mergedItems} maxValue={maxValue} />
          </div>
        )}

        {/* Holdings detail (portfolio-specific flow) */}
        {flow.holding_details?.length > 0 && (
          <div className="pt-3 border-t border-border/30">
            <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
              Your Holdings Flow
            </p>
            <div className="mt-1.5 space-y-1">
              {flow.holding_details.map((holding) => (
                <HoldingRow key={holding.ticker} holding={holding} />
              ))}
            </div>
          </div>
        )}

        {flow.interpretation && (
          <InsightCard>{flow.interpretation}</InsightCard>
        )}
      </div>
    </InsightToggle>
  )
}
