import { useEffect, useRef, useState } from 'react'
import type { TickData, IndexData, StreamStatus } from '../types/stream'

const STREAM_BASE_URL = import.meta.env.VITE_VNSTOCK_API_URL ?? 'https://finance.example.com'

// VN market hours in UTC+7: 9:00-11:30 and 13:00-14:45, Mon-Fri
function isVnMarketOpen(): boolean {
  const now = new Date()
  // Convert to VN time (UTC+7)
  const vnOffset = 7 * 60
  const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes()
  const vnMinutes = (utcMinutes + vnOffset) % (24 * 60)
  const vnDay = new Date(now.getTime() + vnOffset * 60 * 1000).getUTCDay()

  if (vnDay === 0 || vnDay === 6) return false

  const morningOpen = 9 * 60       // 9:00
  const morningClose = 11 * 60 + 30 // 11:30
  const afternoonOpen = 13 * 60    // 13:00
  const afternoonClose = 14 * 60 + 45 // 14:45

  return (
    (vnMinutes >= morningOpen && vnMinutes < morningClose) ||
    (vnMinutes >= afternoonOpen && vnMinutes < afternoonClose)
  )
}

export interface MarketStreamResult {
  prices: Map<string, TickData>
  vnIndex: IndexData | null
  status: StreamStatus | null
  isConnected: boolean
}

/**
 * Subscribe to real-time market price stream via SSE.
 * Only connects during VN market hours; returns empty state outside hours.
 * Rechecks every minute to auto-connect/disconnect as market opens/closes.
 */
export function useMarketStream(symbols: string[]): MarketStreamResult {
  const [prices, setPrices] = useState<Map<string, TickData>>(new Map())
  const [vnIndex, setVnIndex] = useState<IndexData | null>(null)
  const [status, setStatus] = useState<StreamStatus | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const symbolsKey = symbols.slice().sort().join(',')

  useEffect(() => {
    if (symbols.length === 0) return

    function connect() {
      if (!isVnMarketOpen()) return

      const url = `${STREAM_BASE_URL}/stream/prices?symbols=${encodeURIComponent(symbolsKey)}`
      const es = new EventSource(url)
      esRef.current = es

      es.addEventListener('tick', (e) => {
        try {
          const data = JSON.parse(e.data) as Record<string, TickData>
          setPrices((prev) => {
            const next = new Map(prev)
            for (const [ticker, tick] of Object.entries(data)) {
              next.set(ticker, tick)
            }
            return next
          })
        } catch {
          // malformed data — ignore
        }
      })

      es.addEventListener('index', (e) => {
        try {
          setVnIndex(JSON.parse(e.data) as IndexData)
        } catch {
          // ignore
        }
      })

      es.addEventListener('status', (e) => {
        try {
          const s = JSON.parse(e.data) as StreamStatus
          setStatus(s)
          setIsConnected(s.connected)
        } catch {
          // ignore
        }
      })

      es.onopen = () => setIsConnected(true)
      es.onerror = () => setIsConnected(false)
    }

    function disconnect() {
      esRef.current?.close()
      esRef.current = null
      setIsConnected(false)
    }

    function recheckMarketHours() {
      if (isVnMarketOpen()) {
        if (!esRef.current) connect()
      } else {
        if (esRef.current) disconnect()
      }
    }

    connect()
    const timer = setInterval(recheckMarketHours, 60_000)

    return () => {
      clearInterval(timer)
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolsKey])

  return { prices, vnIndex, status, isConnected }
}
