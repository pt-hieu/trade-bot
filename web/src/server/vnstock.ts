/**
 * Server-side helpers for the vnstock API server.
 * All process.env reads are lazy (inside functions) for CF Workers compatibility.
 */

function getVnstockApiUrl(): string {
  const url = process.env.VNSTOCK_API_URL
  if (!url) throw new Error('VNSTOCK_API_URL not configured')
  return url
}

export function getVnstockUrl(): string {
  return getVnstockApiUrl()
}

const DEFAULT_TIMEOUT_MS = 15_000

async function vnstockFetch<T>(
  path: string,
  params: Record<string, string> = {}
): Promise<T | null> {
  let apiUrl: string
  try {
    apiUrl = getVnstockApiUrl()
  } catch {
    return null
  }
  try {
    const url = new URL(`${apiUrl}${path}`)
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v)
    const res = await fetch(url.toString(), {
      signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    })
    if (!res.ok) return null
    return res.json() as T
  } catch {
    return null
  }
}

export interface OhlcvBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type HistoryResponse = { symbol: string; data: OhlcvBar[]; count: number }
type BatchResponse = Record<string, HistoryResponse | { error: string }>

export async function getHistory(ticker: string, days: number): Promise<OhlcvBar[]> {
  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
  const res = await vnstockFetch<HistoryResponse>('/quote/history', {
    symbol: ticker.toUpperCase(),
    interval: '1D',
    start,
    end,
  })
  return res?.data ?? []
}

export async function getHistoryBatch(
  symbols: string[],
  start: string,
  end: string
): Promise<Record<string, OhlcvBar[]>> {
  if (!symbols.length) return {}
  const res = await vnstockFetch<BatchResponse>('/quote/history/batch', {
    symbols: symbols.map((s) => s.toUpperCase()).join(','),
    interval: '1D',
    start,
    end,
  })
  if (!res) return {}
  const out: Record<string, OhlcvBar[]> = {}
  for (const [sym, val] of Object.entries(res)) {
    if ('error' in val) continue
    out[sym] = (val as HistoryResponse).data ?? []
  }
  return out
}

export async function getLatestPrices(
  ticker: string
): Promise<{ close: number; prev_close: number } | null> {
  const bars = await getHistory(ticker, 5)
  if (bars.length < 2) return null
  return {
    close: bars[bars.length - 1].close,
    prev_close: bars[bars.length - 2].close,
  }
}

export async function computeDailyReturn(ticker: string): Promise<number | null> {
  const prices = await getLatestPrices(ticker)
  if (!prices || prices.prev_close === 0) return null
  return (prices.close - prices.prev_close) / prices.prev_close
}

export async function getTechnicals(ticker: string): Promise<Record<string, unknown> | null> {
  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - 60 * 86_400_000).toISOString().slice(0, 10)
  return vnstockFetch<Record<string, unknown>>('/technicals', {
    symbol: ticker.toUpperCase(),
    start,
    end,
  })
}

export async function fetchRsi(ticker: string): Promise<number | null> {
  const data = await getTechnicals(ticker)
  return typeof data?.rsi === 'number' ? Math.round((data.rsi as number) * 100) / 100 : null
}

export async function computeRS(ticker: string): Promise<number | null> {
  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10)
  const batch = await vnstockFetch<BatchResponse>('/quote/history/batch', {
    symbols: [ticker.toUpperCase(), 'VNINDEX'].join(','),
    interval: '1D',
    start,
    end,
  })
  if (!batch) return null

  const tickerData = batch[ticker.toUpperCase()]
  const vnindexData = batch['VNINDEX']
  if (!tickerData || 'error' in tickerData || !vnindexData || 'error' in vnindexData) return null

  const tickerBars = (tickerData as HistoryResponse).data
  const vnindexBars = (vnindexData as HistoryResponse).data
  if (tickerBars.length < 21 || vnindexBars.length < 21) return null

  const tickerReturn = tickerBars[tickerBars.length - 1].close / tickerBars[tickerBars.length - 21].close
  const vnindexReturn = vnindexBars[vnindexBars.length - 1].close / vnindexBars[vnindexBars.length - 21].close
  if (vnindexReturn === 0) return null
  return Math.round((tickerReturn / vnindexReturn) * 1000) / 1000
}
