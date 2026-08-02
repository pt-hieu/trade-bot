import { useMemo, useId } from 'react'
import {
  AreaChart,
  Area,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'

interface SparklineProps {
  data: { close: number }[]
  width?: number | string
  height?: number
  /** Cost basis price in same unit as data (thousands VND) */
  costBasis?: number
  /** Stop loss price in same unit as data (thousands VND) */
  stopPrice?: number
  /** Position P/L percentage — drives line color (green profit, red loss) */
  plPct?: number
}

/**
 * Compute the gradient split offset so the fill is green above costBasis
 * and red below. Returns a 0–1 fraction from the top of the chart.
 */
function computeSplitOffset(
  costBasis: number,
  domainMin: number,
  domainMax: number
): number {
  if (domainMax === domainMin) return 0.5
  const offset = (domainMax - costBasis) / (domainMax - domainMin)
  return Math.max(0.01, Math.min(0.99, offset))
}

export function Sparkline({
  data,
  width = 90,
  height = 28,
  costBasis,
  stopPrice,
  plPct,
}: SparklineProps) {
  const id = useId()
  const safeId = id.replace(/:/g, '')
  const gradientId = `spark-fill-${safeId}`

  if (!data?.length) return null

  // Line color: P/L direction if provided, else price direction
  const isProfit = plPct !== undefined ? plPct >= 0 : data[data.length - 1].close >= data[0].close
  const lineColor = isProfit ? '#10b981' : '#f43f5e'

  // Compute explicit domain including reference values (with 2% padding)
  const { domainMin, domainMax, splitOffset } = useMemo(() => {
    const closes = data.map((point) => point.close)
    const dataMin = Math.min(...closes)
    const dataMax = Math.max(...closes)

    const allValues = [dataMin, dataMax]
    if (costBasis !== undefined) allValues.push(costBasis)
    if (stopPrice !== undefined) allValues.push(stopPrice)

    const rawMin = Math.min(...allValues)
    const rawMax = Math.max(...allValues)
    const range = rawMax - rawMin || 1
    const padding = range * 0.04

    const computedMin = rawMin - padding
    const computedMax = rawMax + padding

    const offset = costBasis !== undefined
      ? computeSplitOffset(costBasis, computedMin, computedMax)
      : null

    return { domainMin: computedMin, domainMax: computedMax, splitOffset: offset }
  }, [data, costBasis, stopPrice])

  const hasCostBasis = costBasis !== undefined && splitOffset !== null

  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
          <YAxis domain={[domainMin, domainMax]} hide />
          <defs>
            {hasCostBasis ? (
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity={0.15} />
                <stop offset={`${splitOffset * 100}%`} stopColor="#10b981" stopOpacity={0.15} />
                <stop offset={`${splitOffset * 100}%`} stopColor="#f43f5e" stopOpacity={0.15} />
                <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.15} />
              </linearGradient>
            ) : (
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.2} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
              </linearGradient>
            )}
          </defs>
          <Area
            type="monotone"
            dataKey="close"
            stroke={lineColor}
            strokeWidth={1.5}
            strokeOpacity={0.8}
            fill={`url(#${gradientId})`}
            dot={false}
            isAnimationActive={false}
          />
          {hasCostBasis && (
            <ReferenceLine
              y={costBasis}
              stroke="#a1a1aa"
              strokeWidth={0.75}
              strokeDasharray="2 2"
              ifOverflow="visible"
            />
          )}
          {stopPrice !== undefined && (
            <ReferenceLine
              y={stopPrice}
              stroke="#f43f5e"
              strokeWidth={0.75}
              strokeOpacity={0.5}
              ifOverflow="visible"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
