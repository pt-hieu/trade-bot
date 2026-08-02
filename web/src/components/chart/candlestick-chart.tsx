import { useEffect, useRef, useState } from 'react'
import { LineStyle, type ISeriesApi } from 'lightweight-charts'
import { AlertCircle } from 'lucide-react'
import { Skeleton } from '../ui/skeleton'
import { ChartToolbar } from './chart-toolbar'
import { useChartInstance } from './use-chart-instance'
import { useChartHistory, useChartTechnicals } from '../../hooks/use-chart-data'
import { useMarketStream } from '../../hooks/use-market-stream'
import { cn } from '../../lib/utils'
import type { ChartInterval, PriceMarker } from '../../types/chart'

interface CandlestickChartProps {
  ticker: string
  /** Fixed pixel height. Omit to fill parent container height (flex-1). */
  height?: number
  priceMarkers?: PriceMarker[]
  className?: string
}

export function CandlestickChart({
  ticker,
  height,
  priceMarkers = [],
  className,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  const [interval, setInterval] = useState<ChartInterval>('1D')
  const [showSma20, setShowSma20] = useState(true)
  const [showSma50, setShowSma50] = useState(true)

  const { chartRef, candleRef, volumeRef, sma20Ref, sma50Ref } = useChartInstance(
    containerRef,
    height
  )

  const { data: history, isLoading, error, refetch } = useChartHistory(ticker, interval)
  const { data: technicals } = useChartTechnicals(ticker)
  const { prices, isConnected } = useMarketStream([ticker])

  // Track last known candle for live merge
  const lastCandleRef = useRef<{ time: string; open: number; high: number; low: number; close: number } | null>(null)
  // Track price lines so we can clear/re-add
  const priceLinesRef = useRef<ReturnType<ISeriesApi<'Custom'>['createPriceLine']>[]>([])

  // Load candle data when history or ticker changes
  useEffect(() => {
    const candle = candleRef.current
    const volume = volumeRef.current
    if (!candle || !volume || !history?.data?.length) return

    const bars = history.data.map((b: any) => ({
      // Daily: use 'yyyy-mm-dd' string. Intraday: Unix timestamp in seconds.
      time: (interval === '1D'
        ? b.time.slice(0, 10)
        : Math.floor(new Date(b.time).getTime() / 1000)
      ) as unknown as import('lightweight-charts').Time,
      open: Number(b.open),
      high: Number(b.high),
      low: Number(b.low),
      close: Number(b.close),
    }))

    const volBars = history.data.map((b: any, i: number) => {
      const isUp = Number(b.close) >= Number(b.open)
      return {
        time: bars[i].time,
        value: Number(b.volume),
        color: isUp ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)',
      }
    })

    ;(candle as any).setData(bars)
    ;(volume as any).setData(volBars)

    const last = bars[bars.length - 1]
    if (last) {
      const raw = history.data[history.data.length - 1]
      lastCandleRef.current = {
        time: last.time as unknown as string,
        open: Number(raw.open),
        high: Number(raw.high),
        low: Number(raw.low),
        close: Number(raw.close),
      }
    }

    const ts = chartRef.current?.timeScale()
    if (ts) {
      ts.setVisibleLogicalRange({ from: bars.length - 60, to: bars.length - 1 })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history, interval])

  // Load SMA overlay data
  useEffect(() => {
    const sma20 = sma20Ref.current
    const sma50 = sma50Ref.current
    if (!sma20 || !sma50 || !technicals?.data?.length || interval !== '1D') return

    const sma20Data = technicals.data
      .filter((b: any) => b.sma20 != null)
      .map((b: any) => ({ time: b.date as unknown as import('lightweight-charts').Time, value: Number(b.sma20) }))
    const sma50Data = technicals.data
      .filter((b: any) => b.sma50 != null)
      .map((b: any) => ({ time: b.date as unknown as import('lightweight-charts').Time, value: Number(b.sma50) }))

    ;(sma20 as any).setData(sma20Data)
    ;(sma50 as any).setData(sma50Data)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [technicals, interval])

  // SMA visibility toggles
  useEffect(() => {
    ;(sma20Ref.current as any)?.applyOptions({ visible: showSma20 })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSma20])

  useEffect(() => {
    ;(sma50Ref.current as any)?.applyOptions({ visible: showSma50 })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSma50])

  // Agent price markers
  useEffect(() => {
    const candle = candleRef.current
    if (!candle) return

    // Clear existing price lines
    priceLinesRef.current.forEach((pl) => {
      try {
        ;(candle as any).removePriceLine(pl)
      } catch {
        // ignore if already removed
      }
    })
    priceLinesRef.current = []

    // Add new price lines
    const styleMap = {
      solid: LineStyle.Solid,
      dashed: LineStyle.Dashed,
      dotted: LineStyle.Dotted,
    }

    priceMarkers.forEach((m) => {
      const pl = (candle as any).createPriceLine({
        price: m.price,
        color: m.color,
        lineWidth: 1,
        lineStyle: styleMap[m.style],
        axisLabelVisible: true,
        title: m.label,
      })
      priceLinesRef.current.push(pl)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priceMarkers])

  // Real-time tick merge
  useEffect(() => {
    const candle = candleRef.current
    const volume = volumeRef.current
    if (!candle || !volume || !isConnected) return

    const tick = prices.get(ticker)
    if (!tick || !lastCandleRef.current) return

    // Normalize: tick.price = raw VND, chart = thousands VND
    const priceK = tick.price / 1000
    const last = lastCandleRef.current

    const updated = {
      time: last.time as unknown as import('lightweight-charts').Time,
      open: last.open,
      high: Math.max(last.high, priceK),
      low: Math.min(last.low, priceK),
      close: priceK,
    }

    ;(candle as any).update(updated)

    const isUp = priceK >= last.open
    ;(volume as any).update({
      time: last.time as unknown as import('lightweight-charts').Time,
      value: tick.volume,
      color: isUp ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)',
    })

    lastCandleRef.current = { ...last, high: updated.high, low: updated.low, close: priceK }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prices, ticker])

  return (
    <div className={cn('relative', height == null && 'flex flex-col', className)}>
      <ChartToolbar
        interval={interval}
        onIntervalChange={setInterval}
        showSma20={showSma20}
        showSma50={showSma50}
        onToggleSma20={() => setShowSma20((v) => !v)}
        onToggleSma50={() => setShowSma50((v) => !v)}
        isConnected={isConnected}
        ticker={ticker}
      />

      {/* Chart container */}
      <div className={cn('relative', height == null && 'flex-1 min-h-0')}>
        <div ref={containerRef} className={height == null ? 'h-full' : undefined} style={height != null ? { height } : undefined} />

        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 flex flex-col gap-2 p-2" style={{ background: '#0a0a0a' }}>
            <Skeleton className="h-full w-full rounded" />
          </div>
        )}

        {/* Error state */}
        {error && !isLoading && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center gap-2"
            style={{ background: '#0a0a0a' }}
          >
            <AlertCircle className="h-5 w-5 text-muted-foreground" />
            <p className="text-xs text-muted-foreground">Failed to load chart data</p>
            <button
              onClick={() => refetch()}
              className="text-xs text-muted-foreground underline cursor-pointer hover:text-foreground"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
