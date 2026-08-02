import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
  type HistogramSeriesOptions,
  type LineSeriesOptions,
} from 'lightweight-charts'

// ── Theme ─────────────────────────────────────────────────────────────────────
const COLORS = {
  bg: '#0a0a0a',
  text: '#71717a',         // zinc-500
  grid: 'rgba(255,255,255,0.04)',
  border: 'rgba(255,255,255,0.08)',
  upColor: '#10b981',      // emerald-500
  downColor: '#f43f5e',    // rose-500
  volUp: 'rgba(16,185,129,0.15)',
  volDown: 'rgba(244,63,94,0.15)',
  sma20: '#fbbf24',        // amber-400
  sma50: '#60a5fa',        // blue-400
}

export interface ChartRefs {
  chartRef: React.MutableRefObject<IChartApi | null>
  candleRef: React.MutableRefObject<ISeriesApi<'Custom'> | null>
  volumeRef: React.MutableRefObject<ISeriesApi<'Custom'> | null>
  sma20Ref: React.MutableRefObject<ISeriesApi<'Custom'> | null>
  sma50Ref: React.MutableRefObject<ISeriesApi<'Custom'> | null>
}

export function useChartInstance(
  containerRef: React.RefObject<HTMLDivElement | null>,
  height: number | undefined
): ChartRefs {
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Custom'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Custom'> | null>(null)
  const sma20Ref = useRef<ISeriesApi<'Custom'> | null>(null)
  const sma50Ref = useRef<ISeriesApi<'Custom'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const resolvedHeight = height ?? (containerRef.current.clientHeight || 400)

    const chart = createChart(containerRef.current, {
      height: resolvedHeight,
      layout: {
        background: { color: COLORS.bg },
        textColor: COLORS.text,
        fontFamily: 'ui-monospace, monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      crosshair: {
        vertLine: { color: COLORS.border, labelBackgroundColor: '#27272a' },
        horzLine: { color: COLORS.border, labelBackgroundColor: '#27272a' },
      },
      rightPriceScale: {
        borderColor: COLORS.border,
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: COLORS.border,
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    })

    // Candlestick series
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.upColor,
      downColor: COLORS.downColor,
      borderUpColor: COLORS.upColor,
      borderDownColor: COLORS.downColor,
      wickUpColor: COLORS.upColor,
      wickDownColor: COLORS.downColor,
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
    } as Partial<CandlestickSeriesOptions>)

    // Volume histogram (overlaid at bottom)
    const volume = chart.addSeries(HistogramSeries, {
      color: COLORS.volUp,
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    } as Partial<HistogramSeriesOptions>)
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    // SMA lines
    const sma20 = chart.addSeries(LineSeries, {
      color: COLORS.sma20,
      lineWidth: 1,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
    } as Partial<LineSeriesOptions>)

    const sma50 = chart.addSeries(LineSeries, {
      color: COLORS.sma50,
      lineWidth: 1,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
    } as Partial<LineSeriesOptions>)

    // Resize observer — update both dimensions when fluid
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          ...(height == null && { height: containerRef.current.clientHeight }),
        })
      }
    })
    observer.observe(containerRef.current)

    chartRef.current = chart
    candleRef.current = candle as unknown as ISeriesApi<'Custom'>
    volumeRef.current = volume as unknown as ISeriesApi<'Custom'>
    sma20Ref.current = sma20 as unknown as ISeriesApi<'Custom'>
    sma50Ref.current = sma50 as unknown as ISeriesApi<'Custom'>

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volumeRef.current = null
      sma20Ref.current = null
      sma50Ref.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height])

  return { chartRef, candleRef, volumeRef, sma20Ref, sma50Ref }
}

export { COLORS, LineStyle }
