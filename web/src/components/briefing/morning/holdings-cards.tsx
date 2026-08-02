import { useMemo, useState } from 'react'
import { ChevronRight, BatteryFull, BatteryMedium, BatteryLow, BatteryWarning } from 'lucide-react'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../../ui/collapsible'
import { Badge } from '../../ui/badge'
import { TooltipProvider } from '../../ui/tooltip'
import { cn, toTitleCase, formatVNDK, formatPct } from '../../../lib/utils'
import type { Recommendation } from '../../../types/intel'
import {
  CardAlert,
  ConvictionDot,
  getConvictionTier,
  RecCardCta,
  ACTION_COLORS,
  EVAL_COLORS,
} from './shared-card-parts'

// ── P/L magnitude → card intensity ──────────────────────────────────────────

function pnlCardStyle(pnl: number | null): { bg: string; ring: string } {
  if (pnl == null) return { bg: 'bg-card/50', ring: '' }
  const abs = Math.abs(pnl)

  if (pnl > 0) {
    if (abs >= 8) return { bg: 'bg-emerald-500/10', ring: 'ring-1 ring-emerald-500/20' }
    if (abs >= 4) return { bg: 'bg-emerald-500/[0.07]', ring: '' }
    return { bg: 'bg-emerald-500/[0.04]', ring: '' }
  }
  if (abs >= 8) return { bg: 'bg-rose-500/10', ring: 'ring-1 ring-rose-500/20' }
  if (abs >= 4) return { bg: 'bg-rose-500/[0.07]', ring: '' }
  return { bg: 'bg-rose-500/[0.04]', ring: '' }
}

function pnlColor(pnl: number): string {
  if (pnl > 0) return 'text-emerald-400'
  if (pnl < 0) return 'text-rose-400'
  return 'text-muted-foreground'
}

// ── Inline floor buffer ─────────────────────────────────────────────────────

function floorBatteryIcon(buffer: number | null) {
  if (buffer == null) return { Icon: BatteryMedium, color: 'text-zinc-600' }
  if (buffer <= 3) return { Icon: BatteryWarning, color: 'text-rose-400' }
  if (buffer <= 7) return { Icon: BatteryLow, color: 'text-amber-400' }
  if (buffer <= 15) return { Icon: BatteryMedium, color: 'text-zinc-500' }
  return { Icon: BatteryFull, color: 'text-zinc-600' }
}

function FloorBadge({ stopPriceVnd, eodPriceVnd }: { stopPriceVnd: number; eodPriceVnd?: number | null }) {
  const buffer = eodPriceVnd
    ? (((Number(eodPriceVnd) - Number(stopPriceVnd)) / Number(eodPriceVnd)) * 100)
    : null

  const { Icon, color } = floorBatteryIcon(buffer)

  return (
    <span className="inline-flex items-center gap-1 text-xs font-mono tabular-nums">
      <span className="text-zinc-500">Floor {formatVNDK(stopPriceVnd)}</span>
      {buffer != null && (
        <span className={cn('inline-flex items-center gap-0.5', color)}>
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span>{buffer.toFixed(0)}%</span>
        </span>
      )}
    </span>
  )
}

// ── Holding card ────────────────────────────────────────────────────────────

function HoldingCard({ rec, showConviction }: { rec: Recommendation; showConviction: boolean }) {
  const [isOpen, setIsOpen] = useState(false)
  const evalStatus = rec.evaluation?.status
  const pnl = rec.evaluation?.pnl_percent != null ? Number(rec.evaluation.pnl_percent) : null
  const eodPrice = rec.evaluation?.eod_price_vnd
  const { bg, ring } = pnlCardStyle(pnl)
  const firstVisibleAlert = rec.alerts.find((alert) => alert.status !== 'cancelled')
  const hasRationale = !!rec.rationale || !!rec.counter_thesis || !!rec.verdict

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className={cn('rounded-lg border border-border/50 px-3 py-2', bg, ring)}>
        {/* Row 1: chevron + ticker + action + price levels + P/L hero */}
        <div className="flex items-center gap-2">
          <CollapsibleTrigger
            disabled={!hasRationale}
            className={cn(
              'flex items-center gap-1.5 shrink-0',
              hasRationale && 'cursor-pointer',
            )}
          >
            {hasRationale && (
              <ChevronRight className={cn(
                'h-3 w-3 text-zinc-500 transition-transform duration-200',
                isOpen && 'rotate-90',
              )} />
            )}
            <span className="font-mono font-bold text-sm tracking-tight">{rec.ticker}</span>
          </CollapsibleTrigger>

          <Badge className={cn('text-xs shrink-0', ACTION_COLORS[rec.action])}>
            {toTitleCase(rec.action)}
          </Badge>

          {/* Price levels */}
          <div className="flex items-center gap-2.5 tabular-nums text-xs min-w-0 overflow-hidden">
            {rec.entry_price_vnd && (
              <span className="font-mono text-zinc-500">
                <span className="text-zinc-600">Entry </span>{formatVNDK(rec.entry_price_vnd)}
              </span>
            )}
            {rec.target_price_vnd && (
              <span className="font-mono text-emerald-600">
                <span className="text-emerald-700">Target </span>{formatVNDK(rec.target_price_vnd)}
              </span>
            )}
            {rec.stop_price_vnd && (
              <FloorBadge stopPriceVnd={rec.stop_price_vnd} eodPriceVnd={eodPrice} />
            )}
          </div>

          <div className="flex-1" />

          {pnl != null && (
            <span className={cn(
              'font-mono font-semibold tabular-nums tracking-tight shrink-0 text-base',
              pnlColor(pnl),
            )}>
              {formatPct(pnl, 1)}
            </span>
          )}
        </div>

        {/* Row 2: alert + eval + conviction + CTA */}
        {(firstVisibleAlert || showConviction || (evalStatus && evalStatus !== rec.action)) && (
          <div className="flex items-center gap-2 mt-1">
            {firstVisibleAlert && (
              <TooltipProvider>
                <CardAlert alert={firstVisibleAlert} />
              </TooltipProvider>
            )}

            {showConviction && <ConvictionDot confidence={rec.strategy_confidence} />}

            <div className="flex-1" />

            <RecCardCta rec={rec} />
          </div>
        )}

        {/* Expanded: rationale + verdict + counter-thesis */}
        <CollapsibleContent>
          <div className="mt-2 pt-2 border-t border-border/20 space-y-1.5 pl-[18px]">
            {rec.verdict && (
              <p className="text-xs font-medium text-foreground">{rec.verdict}</p>
            )}
            {rec.rationale && (
              <p className="text-xs leading-relaxed text-zinc-400">{rec.rationale}</p>
            )}
            {rec.counter_thesis && (
              <p className="text-xs leading-relaxed text-amber-400">{rec.counter_thesis}</p>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Section ─────────────────────────────────────────────────────────────────

export function HoldingsCards({ recs }: { recs: Recommendation[] }) {
  if (recs.length === 0) return null

  const showConviction = useMemo(() => {
    const tiers = new Set(recs.map((rec) => getConvictionTier(rec.strategy_confidence)))
    return tiers.size > 1
  }, [recs])

  return (
    <div className="space-y-1.5">
      {recs.map((rec, index) => (
        <HoldingCard key={`${rec.ticker}-${index}`} rec={rec} showConviction={showConviction} />
      ))}
    </div>
  )
}
