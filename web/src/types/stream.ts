export interface TickData {
  ticker: string
  price: number       // VND (integer)
  change_pct: number
  volume: number
  time: string        // HH:mm:ss
}

export interface IndexData {
  name: string
  value: number
  change_pct: number
  time: string
}

export interface StreamStatus {
  connected: boolean
  symbols: number
  market: 'open' | 'closed' | 'lunch' | 'pre' | 'post'
}
