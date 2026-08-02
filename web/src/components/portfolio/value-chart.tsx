import { useState, useCallback, useMemo } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceDot,
  ReferenceLine,
  ReferenceArea,
} from 'recharts'
import { formatCompact, cn } from '../../lib/utils'
import { formatMinDate, parseDate } from '../../lib/date'
import { ChartTooltip } from './chart-tooltip'
import {
  enrichTradesWithValue,
  groupTradesByDate,
  TradeMarkerDot,
} from './chart-utils'
import {
  type TimeRange,
  TIME_RANGES,
  filterByTimeRange,
} from './chart-alpha'
import type { PortfolioSnapshot, TradeEvent } from '../../types/index'

interface ValueChartProps {
  snapshots: PortfolioSnapshot[]
  trades: TradeEvent[]
  costBasis?: number
  onDateSelect: (date: string) => void
  timeRange: TimeRange
  onTimeRangeChange: (range: TimeRange) => void
}

interface ChartDataPoint {
  snapshot_date: string
  invested_value_vnd: number
  _trades?: Array<TradeEvent & { value: number }>
}

export function ValueChart({
  snapshots,
  trades,
  costBasis,
  onDateSelect,
  timeRange,
  onTimeRangeChange,
}: ValueChartProps) {
  const [refAreaLeft, setRefAreaLeft] = useState<string | null>(null)
  const [refAreaRight, setRefAreaRight] = useState<string | null>(null)
  const [zoomLeft, setZoomLeft] = useState<string | null>(null)
  const [zoomRight, setZoomRight] = useState<string | null>(null)

  const filteredSnapshots = useMemo(
    () => filterByTimeRange(snapshots, timeRange),
    [snapshots, timeRange]
  )

  const enrichedTrades = useMemo(
    () => enrichTradesWithValue(trades, filteredSnapshots),
    [trades, filteredSnapshots]
  )
  const tradesByDate = useMemo(
    () => groupTradesByDate(enrichedTrades),
    [enrichedTrades]
  )

  const chartData: ChartDataPoint[] = useMemo(
    () => filteredSnapshots.map((snapshot) => ({
      snapshot_date: snapshot.snapshot_date,
      invested_value_vnd: snapshot.invested_value_vnd,
      _trades: tradesByDate.get(snapshot.snapshot_date),
    })).filter((dataPoint) => {
      if (!zoomLeft || !zoomRight) return true
      return dataPoint.snapshot_date >= zoomLeft && dataPoint.snapshot_date <= zoomRight
    }),
    [filteredSnapshots, tradesByDate, zoomLeft, zoomRight]
  )

  const costBasisGradient = useMemo(() => {
    if (!costBasis || chartData.length === 0) return null

    const allValues = chartData.map((dataPoint) => dataPoint.invested_value_vnd)
    allValues.push(costBasis)

    const domainMin = Math.min(...allValues)
    const domainMax = Math.max(...allValues)
    const range = domainMax - domainMin
    if (range === 0) return null

    const splitOffset = (domainMax - costBasis) / range
    return {
      splitOffset: Math.max(0.01, Math.min(0.99, splitOffset)),
      domainMin: domainMin - range * 0.02,
      domainMax: domainMax + range * 0.02,
    }
  }, [chartData, costBasis])

  const isZoomed = !!(zoomLeft && zoomRight)

  const handleMouseDown = useCallback((event: { activeLabel?: string }) => {
    if (event?.activeLabel) setRefAreaLeft(event.activeLabel)
  }, [])

  const handleMouseMove = useCallback(
    (event: { activeLabel?: string }) => {
      if (refAreaLeft && event?.activeLabel) setRefAreaRight(event.activeLabel)
    },
    [refAreaLeft],
  )

  const handleMouseUp = useCallback(() => {
    if (refAreaLeft && refAreaRight) {
      const [left, right] = [refAreaLeft, refAreaRight].sort()
      if (left !== right) {
        setZoomLeft(left)
        setZoomRight(right)
      }
    }
    setRefAreaLeft(null)
    setRefAreaRight(null)
  }, [refAreaLeft, refAreaRight])

  const resetZoom = useCallback(() => {
    setZoomLeft(null)
    setZoomRight(null)
  }, [])

  const handleTimeRangeChange = (range: TimeRange) => {
    onTimeRangeChange(range)
    setZoomLeft(null)
    setZoomRight(null)
  }

  if (!chartData.length) return null

  const visibleTradeEntries = [...tradesByDate.entries()].filter(([date]) => {
    if (!zoomLeft || !zoomRight) {
      const cutoff = filteredSnapshots[0]?.snapshot_date
      return !cutoff || date >= cutoff
    }
    return date >= zoomLeft && date <= zoomRight
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <p className="text-[10px] font-medium tracking-widest text-muted-foreground uppercase">
            Portfolio value
          </p>
          {isZoomed && (
            <button
              onClick={resetZoom}
              className="text-[10px] font-medium tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors underline cursor-pointer"
            >
              Reset zoom
            </button>
          )}
        </div>
        <div className="flex gap-1">
          {TIME_RANGES.map((range) => (
            <button
              key={range}
              onClick={() => handleTimeRangeChange(range)}
              className={cn(
                'px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer',
                timeRange === range
                  ? 'bg-foreground/10 text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {range === 'ALL' ? 'All' : range}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-border/50 p-6">
        <div className="mb-4 flex justify-between items-center text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-6 h-0.5 bg-emerald-500 inline-block rounded" />
              Portfolio
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
              Buy
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
              Sell
            </span>
            {costBasis !== undefined && (
              <span className="flex items-center gap-1.5">
                <span className="w-6 h-0 inline-block border-t border-dashed border-zinc-400/60" />
                Cost basis
              </span>
            )}
          </div>
        </div>

        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              onClick={(event) => {
                if (refAreaLeft) return
                const raw = event?.activePayload?.[0]?.payload?.snapshot_date
                if (raw) onDateSelect(parseDate(raw).format('YYYY-MM-DD'))
              }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              style={{ cursor: 'crosshair' }}
            >
              <defs>
                {costBasisGradient ? (
                  <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.15} />
                    <stop offset={`${costBasisGradient.splitOffset * 100}%`} stopColor="#10b981" stopOpacity={0.15} />
                    <stop offset={`${costBasisGradient.splitOffset * 100}%`} stopColor="#f43f5e" stopOpacity={0.1} />
                    <stop offset="100%" stopColor="#f43f5e" stopOpacity={0} />
                  </linearGradient>
                ) : (
                  <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                )}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis
                dataKey="snapshot_date"
                tickFormatter={(dateStr: string) => formatMinDate(dateStr)}
                tick={{ fontSize: 11, fill: '#ffffff' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={costBasisGradient
                  ? [costBasisGradient.domainMin, costBasisGradient.domainMax]
                  : ['auto', 'auto']
                }
                tickFormatter={(value: number) => formatCompact(value)}
                tick={{ fontSize: 11, fill: '#ffffff' }}
                axisLine={false}
                tickLine={false}
                width={60}
              />
              <RechartsTooltip content={<ChartTooltip />} />

              <Area
                type="monotone"
                dataKey="invested_value_vnd"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#portfolioGradient)"
                dot={false}
                isAnimationActive={false}
              />

              {costBasis !== undefined && (
                <ReferenceLine
                  y={costBasis}
                  stroke="#a1a1aa"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  strokeOpacity={0.6}
                  label={{
                    value: `Cost ${formatCompact(costBasis)}`,
                    position: 'right',
                    fill: '#a1a1aa',
                    fontSize: 10,
                  }}
                  ifOverflow="visible"
                />
              )}

              {visibleTradeEntries.map(([date, dateTrades]) => (
                <ReferenceDot
                  key={date}
                  x={date}
                  y={dateTrades[0].value}
                  shape={<TradeMarkerDot trades={dateTrades} />}
                  ifOverflow="extendDomain"
                />
              ))}

              {refAreaLeft && refAreaRight && (
                <ReferenceArea
                  x1={refAreaLeft}
                  x2={refAreaRight}
                  strokeOpacity={0.3}
                  fill="#10b981"
                  fillOpacity={0.1}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
