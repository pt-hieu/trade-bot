import { useState } from 'react'
import { Telescope, ChevronRight } from 'lucide-react'
import { Badge } from '../../ui/badge'
import { TooltipProvider } from '../../ui/tooltip'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../../ui/collapsible'
import { cn, toTitleCase, formatVNDK, formatPct } from '../../../lib/utils'
import type { Recommendation } from '../../../types/intel'
import type { ProximityRec } from './derive-verdict'
import { calcRR } from '../recommendations/shared'
import {
  CardAlert,
  RecCardCta,
  evalCardBackground,
  ACTION_COLORS,
  EVAL_COLORS,
} from './shared-card-parts'

// ── Top pick card ─────────────────────────────────────────────────────────────

function TopPickCard({ rec }: { rec: Recommendation }) {
  const [isOpen, setIsOpen] = useState(false)
  const evalStatus = rec.evaluation?.status
  const pnl = rec.evaluation?.pnl_percent != null ? Number(rec.evaluation.pnl_percent) : null
  const rr = calcRR(rec.entry_price_vnd, rec.stop_price_vnd, rec.target_price_vnd)
  const cardBg = evalCardBackground(evalStatus, pnl)
  const firstVisibleAlert = rec.alerts.find((alert) => alert.status !== 'cancelled')
  const hasRationale = !!rec.rationale
  const hasEval = !!(evalStatus || pnl != null)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className={cn('rounded-lg border border-border/50 px-3 py-2', cardBg)}>
        {/* Row 1: ticker + action + trade levels + R:R hero */}
        <div className="flex items-center gap-2">
          {hasRationale && (
            <CollapsibleTrigger className="flex items-center shrink-0 cursor-pointer">
              <ChevronRight className={cn(
                'h-3 w-3 text-zinc-500 transition-transform duration-200',
                isOpen && 'rotate-90',
              )} />
            </CollapsibleTrigger>
          )}

          <span className="font-mono font-bold text-sm tracking-tight">{rec.ticker}</span>

          <Badge className={cn('text-xs shrink-0', ACTION_COLORS[rec.action])}>
            {toTitleCase(rec.action)}
          </Badge>

          {rec.strategy && (
            <span className="text-xs text-zinc-500">{toTitleCase(rec.strategy)}</span>
          )}

          {/* Trade levels inline */}
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
              <span className="font-mono text-rose-600">
                <span className="text-rose-700">Stop </span>{formatVNDK(rec.stop_price_vnd)}
              </span>
            )}
          </div>

          <div className="flex-1" />

          {rr && (
            <span className="font-mono font-semibold tabular-nums tracking-tight shrink-0 text-base text-zinc-300">
              {rr}R
            </span>
          )}
        </div>

        {/* Row 2: alert + eval + P/L + EOD + CTA */}
        {(firstVisibleAlert || hasEval) && (
          <div className="flex items-center gap-2 mt-1">
            {firstVisibleAlert && (
              <TooltipProvider>
                <CardAlert alert={firstVisibleAlert} />
              </TooltipProvider>
            )}

            {evalStatus && (
              <span className={cn(
                'text-xs font-mono font-medium',
                EVAL_COLORS[evalStatus] ?? 'text-muted-foreground',
              )}>
                {toTitleCase(evalStatus)}
              </span>
            )}

            {pnl != null && (
              <span className={cn(
                'text-xs font-mono tabular-nums font-medium',
                pnl > 0 ? 'text-emerald-400' : pnl < 0 ? 'text-rose-400' : 'text-muted-foreground',
              )}>
                {formatPct(pnl, 1)}
              </span>
            )}

            {rec.evaluation?.eod_price_vnd && (
              <span className="text-xs text-zinc-500 font-mono tabular-nums">
                EOD {formatVNDK(rec.evaluation.eod_price_vnd)}
              </span>
            )}

            <div className="flex-1" />

            <RecCardCta rec={rec} />
          </div>
        )}

        {/* Expanded: rationale */}
        <CollapsibleContent>
          <div className="mt-2 pt-2 border-t border-border/20 pl-[18px]">
            <p className="text-xs leading-relaxed text-zinc-400">{rec.rationale}</p>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function TopPicksEmpty({ closestMiss }: { closestMiss: ProximityRec | null }) {
  if (closestMiss) {
    const { rec, distancePct } = closestMiss
    return (
      <div className="rounded-lg border border-border/40 border-dashed px-4 py-4 space-y-1">
        <div className="flex items-center gap-2 text-zinc-500">
          <Telescope className="h-4 w-4 shrink-0" />
          <span className="text-xs">No setups met criteria. Closest:</span>
        </div>
        <p className="text-xs text-muted-foreground pl-6">
          <span className="font-mono font-medium text-zinc-300">{rec.ticker}</span>
          {' '}entry at{' '}
          <span className="font-mono">{formatVNDK(rec.entry_price_vnd!)}</span>
          {rec.evaluation?.eod_price_vnd && (
            <>
              {' '}— EOD{' '}
              <span className="font-mono">{formatVNDK(rec.evaluation.eod_price_vnd)}</span>
            </>
          )}
          {' '}
          <span className="font-mono text-amber-500">({distancePct.toFixed(1)}% away)</span>
        </p>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-border/40 border-dashed px-4 py-4 text-zinc-500">
      <Telescope className="h-4 w-4 shrink-0" />
      <span className="text-xs">No top picks today — no watchlist setups met risk criteria.</span>
    </div>
  )
}

// ── Section ───────────────────────────────────────────────────────────────────

interface TopPicksCardsProps {
  recs: Recommendation[]
  closestMiss?: ProximityRec | null
}

export function TopPicksCards({ recs, closestMiss = null }: TopPicksCardsProps) {
  if (recs.length === 0) return <TopPicksEmpty closestMiss={closestMiss} />

  return (
    <div className="space-y-1.5">
      {recs.map((rec, index) => (
        <TopPickCard key={`${rec.ticker}-${index}`} rec={rec} />
      ))}
    </div>
  )
}
