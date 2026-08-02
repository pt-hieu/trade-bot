export interface OhlcvBar {
  time: string   // ISO date (daily: "2026-02-25") or ISO datetime (intraday)
  open: number   // thousands VND (e.g. 95.5 = 95,500 VND)
  high: number
  low: number
  close: number
  volume: number
}

export interface ChartHistoryResponse {
  symbol: string
  data: OhlcvBar[]
  count: number
}

export interface TechnicalBar {
  date: string
  close: number | null
  rsi: number | null
  macd: { MACD: number; signal: number; histogram: number } | null
  sma20: number | null
  sma50: number | null
}

export interface ChartTechnicalsResponse {
  symbol: string
  data: TechnicalBar[]
  count: number
}

export type ChartInterval = '1D' | '1H' | '15m'

export interface PriceMarker {
  price: number   // thousands VND (already divided by 1000)
  label: string
  color: string
  style: 'solid' | 'dashed' | 'dotted'
}
