import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { cn } from '../lib/utils'
import { formatPriceVnd } from '../lib/watchlist-utils'
import { CONVICTION_CLASS, TIER_CONFIG } from './longterm/shared'
import { ResearchPanel } from './longterm/research-panel'
import { Plus, TrendingUp, Target } from 'lucide-react'
import type { UnifiedWatchlistItem } from '../lib/watchlist-merge'

interface DetailPanelProps {
  item: UnifiedWatchlistItem
  onNewTrade: (ticker: string, planType: 'SWING' | 'LONGTERM') => void
}

export function WatchlistDetailPanel({ item, onNewTrade }: DetailPanelProps) {
  // Determine section order: most urgent plan's section goes first
  const showSwing = item.plans.includes('swing')
  const showLongterm = item.plans.includes('longterm')
  const swingIsUrgent = item.rsi != null && item.rsi < 50
  const longtermIsUrgent = item.entryProximity?.isInZone ?? false
  const swingFirst = showSwing && showLongterm ? (swingIsUrgent && !longtermIsUrgent) : showSwing

  return (
    <div className="px-4 py-4 space-y-4 bg-muted/5">
      {/* Quick stats bar */}
      <div className="flex flex-wrap gap-3 text-xs">
        {item.currentPrice != null && (
          <span className="text-muted-foreground">
            Price: <span className="font-mono font-medium text-foreground">{formatPriceVnd(item.currentPrice)} VND</span>
          </span>
        )}
        {item.heldShares != null && (
          <span className="text-emerald-400">
            Held: {item.heldShares.toLocaleString()} shares
          </span>
        )}
        {item.stockType && (
          <span className="text-muted-foreground">Type: {item.stockType}</span>
        )}
      </div>

      {/* Sections — order based on urgency */}
      {swingFirst ? (
        <>
          {showSwing && <SwingSection item={item} onNewTrade={onNewTrade} />}
          {showLongterm && <LongtermSection item={item} onNewTrade={onNewTrade} />}
        </>
      ) : (
        <>
          {showLongterm && <LongtermSection item={item} onNewTrade={onNewTrade} />}
          {showSwing && <SwingSection item={item} onNewTrade={onNewTrade} />}
        </>
      )}
    </div>
  )
}

function SwingSection({ item, onNewTrade }: { item: UnifiedWatchlistItem; onNewTrade: DetailPanelProps['onNewTrade'] }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-3.5 w-3.5 text-blue-400" />
          <span className="text-xs font-semibold uppercase tracking-wide text-blue-400">Swing Setup</span>
        </div>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
          onClick={(event) => { event.stopPropagation(); onNewTrade(item.ticker, 'SWING') }}>
          <Plus className="h-3 w-3" /> New Swing Trade
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <span className="text-muted-foreground">RSI</span>
          <div className="mt-0.5">
            {item.rsi != null && item.rsiBadgeClass ? (
              <Badge className={cn('font-mono text-[11px]', item.rsiBadgeClass)}>
                {item.rsi.toFixed(1)} {item.rsiLabel}
              </Badge>
            ) : '--'}
          </div>
        </div>
        {item.swingNotes && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Notes</span>
            <p className="mt-0.5 text-foreground/80">{item.swingNotes}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function LongtermSection({ item, onNewTrade }: { item: UnifiedWatchlistItem; onNewTrade: DetailPanelProps['onNewTrade'] }) {
  const tier = item.tier ? TIER_CONFIG[item.tier] : null

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="h-3.5 w-3.5 text-purple-400" />
          <span className="text-xs font-semibold uppercase tracking-wide text-purple-400">Long-Term</span>
        </div>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
          onClick={(event) => { event.stopPropagation(); onNewTrade(item.ticker, 'LONGTERM') }}>
          <Plus className="h-3 w-3" /> New LT Trade
        </Button>
      </div>

      {/* Key metrics — contained instrument panel */}
      <div className="rounded-lg bg-gradient-to-r from-muted/12 to-muted/4 px-4 py-3">
        <div className="grid grid-cols-4 gap-4">
          <div className="space-y-1">
            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">Entry Zone</span>
            <div className="font-mono text-sm font-medium text-foreground">
              {item.entryZoneVnd != null ? formatPriceVnd(item.entryZoneVnd / 1000) : '--'}
            </div>
            {item.entryProximity && (
              <span className={cn('text-[11px] font-mono font-medium', item.entryProximity.colorClass)}>
                {item.entryProximity.distancePct >= 0 ? '+' : ''}{item.entryProximity.distancePct.toFixed(1)}%
              </span>
            )}
          </div>
          <div className="space-y-1">
            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">Conviction</span>
            <div className="mt-0.5">
              {item.conviction ? (
                <Badge className={cn('text-[10px]', CONVICTION_CLASS[item.conviction])}>
                  {item.conviction}
                </Badge>
              ) : <span className="text-sm text-muted-foreground">--</span>}
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">Tier</span>
            <div className="mt-0.5">
              {tier ? (
                <Badge variant="outline" className={cn('text-[10px]', tier.badgeClass)}>{tier.label}</Badge>
              ) : <span className="text-sm text-muted-foreground">--</span>}
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">Fundamentals</span>
            <div className="text-sm font-mono text-foreground/70">
              {item.peRatio != null ? `P/E ${Number(item.peRatio).toFixed(1)}` : ''}
              {item.peRatio != null && item.roe != null ? ' · ' : ''}
              {item.roe != null ? `ROE ${Number(item.roe).toFixed(1)}%` : ''}
              {item.peRatio == null && item.roe == null && '--'}
            </div>
          </div>
        </div>
      </div>

      {/* Research — verdict → signals + risks → collapsed prose */}
      <ResearchPanel ticker={item.ticker} reviewFlags={item.reviewFlags}
        entryZoneVnd={item.entryZoneVnd} entryProximity={item.entryProximity} />
    </div>
  )
}
