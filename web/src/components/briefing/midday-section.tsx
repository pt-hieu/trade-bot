import { useMemo, type ReactNode } from 'react'
import { Badge } from '../ui/badge'
import { InsightToggle, InsightTrigger, InsightCard } from '../ui/detail-text'
import { TrendingUp, TrendingDown, ArrowRight } from 'lucide-react'
import { toTitleCase, formatVNDK } from '../../lib/utils'
import type { MiddayCheckData, MorningPositionAlert } from '../../types/intel'

function highlightTickers(text: string, knownTickers: Set<string>): ReactNode {
  if (knownTickers.size === 0) return text
  const pattern = new RegExp(`\\b(${[...knownTickers].join('|')})\\b`, 'g')
  const parts = text.split(pattern)
  return parts.map((part, index) =>
    knownTickers.has(part)
      ? <span key={index} className="font-mono font-semibold text-foreground">{part}</span>
      : part
  )
}

interface MiddaySectionProps {
  data: MiddayCheckData
}

function urgencyConfig(urgency: string) {
  if (urgency === 'high') return {
    bg: 'bg-rose-500/10',
    text: 'text-rose-400',
    label: 'High',
  }
  if (urgency === 'medium') return {
    bg: 'bg-amber-500/8',
    text: 'text-amber-400',
    label: 'Med',
  }
  return {
    bg: 'bg-muted/30',
    text: 'text-muted-foreground',
    label: 'Low',
  }
}

function actionColor(action: string) {
  if (['TRIM', 'EXIT', 'SELL'].includes(action)) return 'bg-rose-500/15 text-rose-400 border-rose-500/20'
  if (['BUY', 'ADD', 'LIMIT_BUY'].includes(action)) return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
  return 'bg-muted/40 text-muted-foreground border-border'
}

function overrideStatusColor(status: string) {
  if (status === 'CANCEL') return 'bg-rose-500/15 text-rose-400 border-rose-500/20'
  if (status === 'ADJUST') return 'bg-amber-500/15 text-amber-400 border-amber-500/20'
  return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
}

function formatK(vnd: number | null | undefined) {
  if (vnd == null) return null
  return `${formatVNDK(vnd)}k`
}

function PositionAlertRow({ a }: { a: MorningPositionAlert }) {
  const urg = urgencyConfig(a.urgency)
  const prices = [
    a.entry_price != null ? `E ${formatK(a.entry_price)}` : null,
    a.stop_price != null ? `S ${formatK(a.stop_price)}` : null,
    a.target_price != null ? `T ${formatK(a.target_price)}` : null,
  ].filter(Boolean) as string[]

  return (
    <InsightToggle>
      <div className={`${urg.bg} px-3 py-2 rounded-lg`}>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono font-bold text-sm tracking-tight">{a.ticker}</span>
          <Badge className={`text-xs ${actionColor(a.action)}`}>{a.action}</Badge>
          <span className={`text-xs font-semibold uppercase tracking-wider ${urg.text}`}>{urg.label}</span>
          {a.reason && <InsightTrigger className="ml-auto" />}
          {a.pct_from_entry != null && (
            <span className={`text-xs font-mono ${Number(a.pct_from_entry) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {Number(a.pct_from_entry) > 0 ? '+' : ''}{Number(a.pct_from_entry).toFixed(1)}%
            </span>
          )}
          {a.weight_pct != null && (
            <span className="text-xs font-mono text-zinc-500">{Number(a.weight_pct).toFixed(1)}% wt</span>
          )}
        </div>
        {prices.length > 0 && (
          <div className="flex gap-3 mt-1.5">
            {prices.map((p) => (
              <span key={p} className="text-xs font-mono text-zinc-600">{p}</span>
            ))}
          </div>
        )}
        {a.reason && <InsightCard className="mt-2">{a.reason}</InsightCard>}
      </div>
    </InsightToggle>
  )
}

export function MiddaySection({ data }: MiddaySectionProps) {
  const morningAlerts = data.morning_position_alerts ?? []
  const overrides = data.recommendation_overrides ?? []

  const knownTickers = useMemo(() => new Set([
    ...data.entries_hit.map(entry => entry.ticker),
    ...data.big_movers.map(mover => mover.ticker),
    ...data.position_alerts.map(alert => alert.ticker),
    ...morningAlerts.map(alert => alert.ticker),
    ...overrides.map(override => override.ticker),
  ]), [data.entries_hit, data.big_movers, data.position_alerts, morningAlerts, overrides])

  const sortedBigMovers = useMemo(
    () => [...data.big_movers].sort((a, b) => Math.abs(Number(b.change_pct)) - Math.abs(Number(a.change_pct))),
    [data.big_movers],
  )

  const hasSignals = data.entries_hit.length > 0 || data.big_movers.length > 0 ||
    data.position_alerts.length > 0 || data.morning_reflection || data.afternoon_plan ||
    morningAlerts.length > 0 || overrides.length > 0

  const tradingModeColor = data.trading_mode === 'LOW_CASH'
    ? 'bg-amber-500/15 text-amber-400 border-amber-500/20'
    : data.trading_mode === 'REALLOCATION'
    ? 'bg-rose-500/15 text-rose-400 border-rose-500/20'
    : 'bg-secondary text-secondary-foreground'

  const hasReflection = !!(data.morning_reflection || data.afternoon_plan)

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2.5">
        <Badge className={`text-xs ${tradingModeColor}`}>{toTitleCase(data.trading_mode)}</Badge>
      </div>

      {!hasSignals && (
        <p className="text-sm text-muted-foreground">
          No midday signals — no entries hit and no significant moves during the morning session.
        </p>
      )}

      {morningAlerts.length > 0 && (
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase mb-2.5">
            Morning Position Monitor
          </p>
          <div className="space-y-2">
            {morningAlerts.map((a) => (
              <PositionAlertRow key={a.ticker} a={a} />
            ))}
          </div>
        </div>
      )}

      {data.entries_hit.length > 0 && (
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase mb-2">
            Entries Hit
          </p>
          <div className="flex gap-2 flex-wrap">
            {data.entries_hit.map((e) => (
              <Badge key={e.ticker} className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 font-mono text-xs">
                {e.ticker}
                {e.current_price_vnd && (
                  <span className="ml-1 opacity-60">{formatK(Number(e.current_price_vnd))}</span>
                )}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {data.big_movers.length > 0 && (
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase mb-2">
            Big Movers
          </p>
          <div className="flex gap-2 flex-wrap">
            {sortedBigMovers.map((m) => {
                const pct = Number(m.change_pct)
                const absPct = Math.abs(pct)
                const up = pct >= 0
                const tier = absPct >= 5
                  ? { size: 'text-sm', weight: 'font-bold', opacity: '/15', pad: 'px-3 py-1.5' }
                  : absPct >= 3
                  ? { size: 'text-xs', weight: 'font-semibold', opacity: '/10', pad: 'px-2.5 py-1' }
                  : { size: 'text-xs', weight: 'font-medium', opacity: '/5', pad: 'px-2 py-0.5' }
                return (
                  <div
                    key={m.ticker}
                    className={`flex items-center gap-1.5 ${tier.pad} rounded-md border ${
                      up
                        ? `bg-emerald-500${tier.opacity} border-emerald-500/15`
                        : `bg-rose-500${tier.opacity} border-rose-500/15`
                    }`}
                  >
                    {up
                      ? <TrendingUp className="w-3 h-3 text-emerald-400 shrink-0" />
                      : <TrendingDown className="w-3 h-3 text-rose-400 shrink-0" />
                    }
                    <span className={`${tier.size} font-mono ${tier.weight}`}>{m.ticker}</span>
                    <span className={`${tier.size} font-mono ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {up ? '+' : ''}{pct.toFixed(1)}%
                    </span>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {hasReflection && (
        <InsightToggle defaultOpen>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">Session Notes</p>
              <InsightTrigger />
            </div>
            <InsightCard>
              <div className="space-y-3">
                {data.morning_reflection && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-sky-500 mb-1">Morning</p>
                    <p className="leading-relaxed">{highlightTickers(data.morning_reflection, knownTickers)}</p>
                  </div>
                )}
                {data.afternoon_plan && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-amber-500 mb-1">Afternoon</p>
                    <p className="leading-relaxed">{highlightTickers(data.afternoon_plan, knownTickers)}</p>
                  </div>
                )}
              </div>
            </InsightCard>
          </div>
        </InsightToggle>
      )}

      {overrides.length > 0 && (
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase mb-2.5">
            Recommendation Overrides
          </p>
          <div className="space-y-2">
            {overrides.map((o) => (
              <div key={o.ticker} className="bg-muted/20 px-3 py-2 rounded-lg space-y-0.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-bold text-sm">{o.ticker}</span>
                  <span className="text-xs text-zinc-500">{o.morning_action}</span>
                  <ArrowRight className="w-3 h-3 text-zinc-600" />
                  <Badge className={`text-xs ${overrideStatusColor(o.midday_status)}`}>
                    {o.midday_status}
                  </Badge>
                </div>
                {o.reason && (
                  <p className="text-xs text-muted-foreground leading-relaxed">{o.reason}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {data.position_alerts.length > 0 && (
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase mb-2">
            Price Level Alerts
          </p>
          <div className="space-y-1">
            {data.position_alerts.map((a) => {
              const urg = urgencyConfig(a.urgency ?? 'low')
              return (
                <div key={a.ticker} className="flex items-center gap-2.5 text-xs">
                  <span className="font-mono font-semibold">{a.ticker}</span>
                  <Badge variant="outline" className="text-xs">{toTitleCase(a.level_type)}</Badge>
                  <span className="font-mono tabular-nums text-muted-foreground">
                    {a.distance_pct != null ? `${Number(a.distance_pct).toFixed(1)}%` : '—'}
                  </span>
                  <span className={`text-xs font-medium ${urg.text}`}>{toTitleCase(a.urgency)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
