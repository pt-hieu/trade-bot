import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { formatCompact, formatPct } from '../../lib/utils'
import type { PortfolioSummary } from '../../types/index'

function StatCard({
  label,
  value,
  subtitle,
  gradient,
}: {
  label: string
  value: string
  subtitle?: string
  gradient?: 'positive' | 'negative' | 'none'
}) {
  return (
    <Card gradient={gradient ?? 'none'} className="border-border/50 py-3 px-4 gap-1 flex-1 min-w-[140px]">
      <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">{label}</p>
      <p className="text-lg font-semibold font-mono tabular-nums">{value}</p>
      {subtitle && <p className="text-xs text-muted-foreground font-mono tabular-nums">{subtitle}</p>}
    </Card>
  )
}

const TREND_ICON = {
  up: TrendingUp,
  down: TrendingDown,
  flat: Minus,
}

const TREND_COLOR = {
  up: 'text-emerald-400',
  down: 'text-rose-400',
  flat: 'text-muted-foreground',
}

export function SummaryStrip({ summary }: { summary: PortfolioSummary }) {
  const totalReturnSign = summary.totalReturn >= 0 ? '+' : ''
  const alphaSign = summary.alphaVsVnindex >= 0 ? '+' : ''
  const unrealizedSign = summary.unrealizedPl >= 0 ? '+' : ''
  const realizedSign = summary.realizedPl >= 0 ? '+' : ''

  const TrendIcon = TREND_ICON[summary.unrealizedTrend]
  const trendColor = TREND_COLOR[summary.unrealizedTrend]

  return (
    <div className="flex gap-3 flex-wrap">
      <StatCard
        label="Total return"
        value={`${totalReturnSign}${formatCompact(summary.totalReturn)}`}
        subtitle={`${totalReturnSign}${summary.totalReturnPct.toFixed(1)}%`}
        gradient={summary.totalReturn >= 0 ? 'positive' : 'negative'}
      />
      <StatCard
        label="Alpha vs VN-Index"
        value={`${alphaSign}${summary.alphaVsVnindex.toFixed(1)}%`}
        subtitle={`VNI: ${summary.vnindexReturnPct >= 0 ? '+' : ''}${summary.vnindexReturnPct.toFixed(1)}%`}
        gradient={summary.alphaVsVnindex >= 0 ? 'positive' : 'negative'}
      />
      <Card
        gradient={summary.unrealizedPl >= 0 ? 'positive' : 'negative'}
        className="border-border/50 py-3 px-4 gap-1 flex-1 min-w-[140px]"
      >
        <div className="flex items-center gap-1.5">
          <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">Unrealized P/L</p>
          <TrendIcon className={`h-3 w-3 ${trendColor}`} />
        </div>
        <p className="text-lg font-semibold font-mono tabular-nums">
          {unrealizedSign}{formatCompact(summary.unrealizedPl)}
        </p>
        <p className="text-xs text-muted-foreground font-mono tabular-nums">
          {formatPct(summary.unrealizedPlPct)}
        </p>
      </Card>
      <StatCard
        label="Realized P/L"
        value={`${realizedSign}${formatCompact(summary.realizedPl)}`}
        subtitle={`${summary.closedTradeCount} closed trades`}
        gradient={summary.realizedPl >= 0 ? 'positive' : 'negative'}
      />
      <StatCard
        label="Cash deployed"
        value={`${Math.round(summary.cashDeployedPct)}%`}
        subtitle={`${formatCompact(summary.cashAvailable)} available`}
      />
    </div>
  )
}

export function SummaryStripSkeleton() {
  return (
    <div className="flex gap-3 flex-wrap">
      {Array.from({ length: 5 }).map((_, index) => (
        <Skeleton key={index} className="h-20 flex-1 min-w-[140px]" />
      ))}
    </div>
  )
}
