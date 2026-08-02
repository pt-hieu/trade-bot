import { useMemo, useId } from 'react'
import { AreaChart, Area, XAxis, YAxis, ReferenceLine, ResponsiveContainer } from 'recharts'
import { filterByTimeRange, buildVnindexLookup, type TimeRange } from './chart-alpha'
import type { PortfolioSnapshot, VnindexDataPoint } from '../../types/index'

interface ReturnStripProps {
  snapshots: PortfolioSnapshot[]
  vnindex: VnindexDataPoint[]
  timeRange: TimeRange
}

interface ReturnDataPoint {
  date: string
  portfolioReturn: number
  vnindexReturn: number | undefined
  /** Portfolio return minus VN-Index return — positive = outperforming */
  alpha: number | undefined
}

export function ReturnStrip({ snapshots, vnindex, timeRange }: ReturnStripProps) {
  const id = useId()
  const safeId = id.replace(/:/g, '')

  const data: ReturnDataPoint[] = useMemo(() => {
    const filtered = filterByTimeRange(snapshots, timeRange)
    if (filtered.length === 0) return []

    const vnindexLookup = buildVnindexLookup(vnindex, filtered)
    const firstPortfolioValue = filtered[0].invested_value_vnd
    const firstVnindexValue = vnindexLookup.get(filtered[0].snapshot_date)

    return filtered.map((snapshot) => {
      const portfolioReturn = firstPortfolioValue > 0
        ? ((snapshot.invested_value_vnd - firstPortfolioValue) / firstPortfolioValue) * 100
        : 0

      const vnindexValue = vnindexLookup.get(snapshot.snapshot_date)
      const vnindexReturn = vnindexValue !== undefined && firstVnindexValue !== undefined && firstVnindexValue > 0
        ? ((vnindexValue - firstVnindexValue) / firstVnindexValue) * 100
        : undefined

      return {
        date: snapshot.snapshot_date,
        portfolioReturn,
        vnindexReturn,
        alpha: vnindexReturn !== undefined ? portfolioReturn - vnindexReturn : undefined,
      }
    })
  }, [snapshots, vnindex, timeRange])

  const splitOffset = useMemo(() => {
    const alphaValues = data.map((point) => point.alpha).filter((value): value is number => value !== undefined)
    if (alphaValues.length === 0) return null

    const min = Math.min(...alphaValues)
    const max = Math.max(...alphaValues)
    const range = max - min
    if (range === 0) return 0.5

    return Math.max(0.01, Math.min(0.99, (max - 0) / range))
  }, [data])

  if (data.length < 2 || splitOffset === null) return null

  return (
    <div className="rounded-lg border border-border/50 px-6 py-2">
      <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase mb-1">
        % return vs VN-Index
      </p>
      <div className="h-[60px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`alphaFill-${safeId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity={0.2} />
                <stop offset={`${splitOffset * 100}%`} stopColor="#10b981" stopOpacity={0.08} />
                <stop offset={`${splitOffset * 100}%`} stopColor="#f43f5e" stopOpacity={0.08} />
                <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.2} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis hide />
            <ReferenceLine y={0} stroke="hsl(var(--border))" strokeOpacity={0.4} />

            {/* Alpha spread: filled green above 0 (outperforming), red below (underperforming) */}
            <Area
              type="monotone"
              dataKey="alpha"
              stroke="none"
              fill={`url(#alphaFill-${safeId})`}
              isAnimationActive={false}
              dot={false}
              connectNulls
            />

            {/* Portfolio return: green solid */}
            <Area
              type="monotone"
              dataKey="portfolioReturn"
              stroke="#10b981"
              strokeWidth={1.5}
              fill="none"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
