import { createServerFn } from '@tanstack/react-start'
import { getVnstockUrl } from '../vnstock'

const LOOKBACK_DAILY = 200
const LOOKBACK_INTRADAY = 5 // days
const LOOKBACK_BATCH_DAYS = 30

export const getChartHistory = createServerFn({ method: 'GET' })
  .inputValidator(
    (data: { symbol: string; interval?: string; start?: string; end?: string }) => data,
  )
  .handler(async ({ data }) => {
    const interval = data.interval ?? '1D'
    const now = new Date()
    const end = data.end ?? now.toISOString().slice(0, 10)
    const lookbackDays = interval === '1D' ? LOOKBACK_DAILY : LOOKBACK_INTRADAY
    const defaultStart = new Date(now.getTime() - lookbackDays * 86_400_000)
      .toISOString()
      .slice(0, 10)
    const start = data.start ?? defaultStart

    const vnstockUrl = getVnstockUrl()
    const url = new URL(`${vnstockUrl}/quote/history`)
    url.searchParams.set('symbol', data.symbol.toUpperCase())
    url.searchParams.set('interval', interval)
    url.searchParams.set('start', start)
    url.searchParams.set('end', end)

    const res = await fetch(url.toString(), { signal: AbortSignal.timeout(20_000) })
    if (!res.ok) throw new Error(`Upstream error: ${res.status}`)
    return res.json()
  })

export const getChartHistoryBatch = createServerFn({ method: 'GET' })
  .inputValidator((data: { symbols: string; days?: number }) => data)
  .handler(async ({ data }) => {
    const days = data.days ?? LOOKBACK_BATCH_DAYS
    const now = new Date()
    const end = now.toISOString().slice(0, 10)
    const start = new Date(now.getTime() - days * 86_400_000).toISOString().slice(0, 10)

    const vnstockUrl = getVnstockUrl()
    const url = new URL(`${vnstockUrl}/quote/history/batch`)
    url.searchParams.set('symbols', data.symbols.toUpperCase())
    url.searchParams.set('interval', '1D')
    url.searchParams.set('start', start)
    url.searchParams.set('end', end)

    const res = await fetch(url.toString(), { signal: AbortSignal.timeout(30_000) })
    if (!res.ok) throw new Error(`Upstream error: ${res.status}`)
    return res.json()
  })

export const getChartTechnicals = createServerFn({ method: 'GET' })
  .inputValidator((data: { symbol: string }) => data)
  .handler(async ({ data }) => {
    const vnstockUrl = getVnstockUrl()
    const url = new URL(`${vnstockUrl}/technicals/history`)
    url.searchParams.set('symbol', data.symbol.toUpperCase())
    url.searchParams.set('source', 'VCI')

    const res = await fetch(url.toString(), { signal: AbortSignal.timeout(20_000) })
    if (!res.ok) throw new Error(`Upstream error: ${res.status}`)
    return res.json()
  })
