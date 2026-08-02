import { useEffect, useRef } from 'react'
import { useChartInstance } from '../../chart/use-chart-instance'
import type { PriceChartData } from '../../../lib/chat/data-parts'

const CHART_HEIGHT = 220

interface PriceChartRendererProps {
  data: PriceChartData
}

export function PriceChartRenderer({ data }: PriceChartRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { chartRef, candleRef, volumeRef } = useChartInstance(containerRef, CHART_HEIGHT)

  useEffect(() => {
    const candle = candleRef.current
    const volume = volumeRef.current
    if (!candle || !volume || !data.candles?.length) return

    const bars = data.candles.map((b) => ({
      time: b.time.slice(0, 10) as unknown as import('lightweight-charts').Time,
      open: Number(b.open),
      high: Number(b.high),
      low: Number(b.low),
      close: Number(b.close),
    }))

    const volBars = data.candles.map((b, i) => ({
      time: bars[i].time,
      value: Number(b.volume),
      color:
        Number(b.close) >= Number(b.open)
          ? 'rgba(16,185,129,0.15)'
          : 'rgba(244,63,94,0.15)',
    }))

    ;(candle as any).setData(bars)
    ;(volume as any).setData(volBars)

    const ts = chartRef.current?.timeScale()
    if (ts) {
      ts.setVisibleLogicalRange({ from: bars.length - 60, to: bars.length - 1 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  if (!data.candles?.length) return null

  return (
    <div className="rounded border border-border/20 overflow-hidden my-1">
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/20">
        <span className="text-[10px] font-mono text-foreground/50 tracking-wider">
          {data.ticker}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground/30">
          {data.candles.length}d · 1D
        </span>
      </div>
      <div ref={containerRef} style={{ height: CHART_HEIGHT }} />
    </div>
  )
}
