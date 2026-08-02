import { useMemo } from 'react'
import { Card } from '../../ui/card'
import { Badge } from '../../ui/badge'
import { cn, toTitleCase, formatVNDK } from '../../../lib/utils'
import { ACTION_COLORS } from '../recommendations/shared'
import type { Recommendation } from '../../../types/intel'
import type { ProximityRec } from './derive-verdict'
import {
  type ConvictionTier,
  getConvictionTier,
  CONVICTION_DOT_CLASS,
  CONVICTION_LABEL,
  InlineRationale,
} from './shared-card-parts'

// ── Proximity badge ─────────────────────────────────────────────────────────

function proximityColor(distancePct: number): string {
  const abs = Math.abs(distancePct)
  if (abs <= 3) return 'text-emerald-400 bg-emerald-500/15'
  if (abs <= 8) return 'text-amber-400 bg-amber-500/10'
  return 'text-zinc-500 bg-muted/30'
}

function proximityLabel(distancePct: number): string {
  if (distancePct <= 0) return 'In zone'
  return `${distancePct.toFixed(1)}% away`
}

// ── Parse conviction from rationale text ─────────────────────────────────────

function parseConvictionFromRationale(rationale: string | null): ConvictionTier | null {
  if (!rationale) return null
  const match = rationale.match(/\((\w[\w-]*)\s+conviction\)/i)
  if (!match) return null
  const level = match[1].toLowerCase()
  if (level === 'high') return 'high'
  if (level === 'medium' || level.startsWith('medium')) return 'medium'
  return 'low'
}

function resolveConviction(rec: Recommendation): ConvictionTier {
  if (rec.strategy_confidence != null) return getConvictionTier(rec.strategy_confidence)
  return parseConvictionFromRationale(rec.rationale) ?? 'low'
}

// ── Conviction card bg ──────────────────────────────────────────────────────

const CONVICTION_CARD_BG: Record<ConvictionTier, string> = {
  high: 'bg-emerald-500/5',
  medium: 'bg-card/50',
  low: 'bg-card/30',
}

// ── Zone card (near zones — full card) ─────────────────────────────────────

interface ZoneCardProps {
  rec: Recommendation
  distancePct: number | null
  tier: ConvictionTier
}

function ZoneCard({ rec, distancePct, tier }: ZoneCardProps) {
  const isNearZone = distancePct != null && Math.abs(distancePct) <= 3

  return (
    <Card
      className={cn(
        'rounded-lg border border-border/50 p-3 space-y-2',
        CONVICTION_CARD_BG[tier],
        isNearZone && 'ring-1 ring-emerald-500/15',
      )}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono font-bold text-sm">{rec.ticker}</span>

        {rec.action && (
          <Badge className={cn('text-xs', ACTION_COLORS[rec.action])}>
            {toTitleCase(rec.action)}
          </Badge>
        )}

        {distancePct != null && (
          <span className={cn(
            'text-xs font-mono tabular-nums px-1.5 py-0.5 rounded',
            proximityColor(distancePct),
          )}>
            {proximityLabel(distancePct)}
          </span>
        )}

        <span className="inline-flex items-center gap-1 ml-auto">
          <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', CONVICTION_DOT_CLASS[tier])} />
          <span className="text-xs text-muted-foreground">{CONVICTION_LABEL[tier]}</span>
        </span>
      </div>

      {/* Price comparison row */}
      {rec.entry_price_vnd && (
        <div className="flex items-center gap-4 font-mono tabular-nums text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-500">Entry</span>
            <span className="text-zinc-300 font-medium">{formatVNDK(rec.entry_price_vnd)}</span>
          </div>
          {rec.evaluation?.eod_price_vnd && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-500">Now</span>
              <span className={cn(
                'font-medium',
                isNearZone ? 'text-emerald-400' : 'text-zinc-400',
              )}>
                {formatVNDK(rec.evaluation.eod_price_vnd)}
              </span>
            </div>
          )}
        </div>
      )}

      <InlineRationale rationale={rec.rationale} />
    </Card>
  )
}

// ── Far zone row (15%+ away — compact single-line) ─────────────────────────

function FarZoneRow({ rec, distancePct, tier }: ZoneCardProps) {
  return (
    <div className="flex items-center gap-2 py-1.5 px-2.5 rounded-md bg-card/30 hover:bg-card/50 transition-colors">
      <span className={cn('h-1 w-1 rounded-full shrink-0', CONVICTION_DOT_CLASS[tier])} />
      <span className="font-mono font-medium text-xs w-12 shrink-0 text-zinc-300">{rec.ticker}</span>

      {rec.action && (
        <Badge className={cn('text-xs px-1 py-0', ACTION_COLORS[rec.action])}>
          {toTitleCase(rec.action)}
        </Badge>
      )}

      {rec.entry_price_vnd && (
        <span className="text-xs font-mono tabular-nums text-zinc-500">
          @ {formatVNDK(rec.entry_price_vnd)}
        </span>
      )}

      {distancePct != null && (
        <span className="text-xs font-mono tabular-nums text-zinc-600 ml-auto">
          {distancePct.toFixed(0)}% away
        </span>
      )}
    </div>
  )
}

// ── Section ─────────────────────────────────────────────────────────────────

const FAR_ZONE_THRESHOLD = 15

interface WatchlistChangesProps {
  recs: Recommendation[]
  proximityData: ProximityRec[]
}

export function WatchlistChanges({ recs, proximityData }: WatchlistChangesProps) {
  const distanceMap = useMemo(() => {
    const map = new Map<string, number>()
    for (const item of proximityData) {
      if (item.distancePct !== Infinity) {
        map.set(item.rec.ticker, item.distancePct)
      }
    }
    return map
  }, [proximityData])

  const { nearRecs, farRecs } = useMemo(() => {
    const sorted = [...recs].sort((recA, recB) => {
      const distA = distanceMap.get(recA.ticker)
      const distB = distanceMap.get(recB.ticker)
      if (distA != null && distB != null) return Math.abs(distA) - Math.abs(distB)
      if (distA != null) return -1
      if (distB != null) return 1
      return recA.ticker.localeCompare(recB.ticker)
    })
    const near: Recommendation[] = []
    const far: Recommendation[] = []
    for (const rec of sorted) {
      const dist = distanceMap.get(rec.ticker)
      if (dist != null && Math.abs(dist) >= FAR_ZONE_THRESHOLD) {
        far.push(rec)
      } else {
        near.push(rec)
      }
    }
    return { nearRecs: near, farRecs: far }
  }, [recs, distanceMap])

  if (recs.length === 0) return null

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
        Long-term Zones
      </h3>

      {/* Near zones — full cards */}
      {nearRecs.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {nearRecs.map((rec, index) => {
            const tier = resolveConviction(rec)
            const distance = distanceMap.get(rec.ticker) ?? null
            const isNearZone = distance != null && Math.abs(distance) <= 3
            return (
              <div
                key={`${rec.ticker}-${index}`}
                className={cn(
                  (tier === 'high' || isNearZone) && 'lg:col-span-2',
                )}
              >
                <ZoneCard rec={rec} distancePct={distance} tier={tier} />
              </div>
            )
          })}
        </div>
      )}

      {/* Far zones — compact single-line rows */}
      {farRecs.length > 0 && (
        <div className="space-y-0.5">
          {farRecs.map((rec, index) => (
            <FarZoneRow
              key={`${rec.ticker}-${index}`}
              rec={rec}
              distancePct={distanceMap.get(rec.ticker) ?? null}
              tier={resolveConviction(rec)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
