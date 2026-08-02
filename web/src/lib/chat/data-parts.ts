/**
 * DataUIPart types, Zod schemas, and tool→data-part registry.
 *
 * Triggers: when agent calls a tool with render:true, the server intercepts
 * the tool result in the delegation tool execute and pushes a matching data-* part
 * via the UIMessageStreamWriter. The client renders it as a React component inline.
 */
import type { UIMessage } from 'ai'
import { z } from 'zod'
import type { OhlcvBar, ChartHistoryResponse } from '../../types/chart'

// ─── Payload Types ─────────────────────────────────────────────────────────

export interface PriceChartData {
  ticker: string
  candles: OhlcvBar[]
}

// ─── UIMessage Generic ──────────────────────────────────────────────────────

export interface UsageData {
  inputTokens: number
  outputTokens: number
  contextWindow: number
}

export type SwingyDataParts = {
  'price-chart': PriceChartData
  'portfolio-table': unknown[]
  'trades-table': unknown[]
  'watchlist-table': unknown[]
  'alerts-card': unknown[]
  'market-context': unknown
  'usage': UsageData
}

export type SwingyUIMessage = UIMessage<unknown, SwingyDataParts>

// ─── Zod Schemas (client validation via dataPartSchemas in useChat) ─────────
// Keys are WITHOUT the `data-` prefix (as required by ChatInit.dataPartSchemas)

export const dataPartSchemas = {
  'price-chart': z.object({
    ticker: z.string(),
    candles: z.array(
      z.object({
        time: z.string(),
        open: z.number(),
        high: z.number(),
        low: z.number(),
        close: z.number(),
        volume: z.number(),
      }),
    ),
  }),
  'portfolio-table': z.array(z.unknown()),
  'trades-table': z.array(z.unknown()),
  'watchlist-table': z.array(z.unknown()),
  'alerts-card': z.array(z.unknown()),
  'market-context': z.unknown(),
  'usage': z.object({
    inputTokens: z.number(),
    outputTokens: z.number(),
    contextWindow: z.number(),
  }),
}

// ─── Tool → Data Part Mapping ──────────────────────────────────────────────

export interface ToolDataMapping {
  partType: keyof SwingyDataParts
  transform: (output: unknown, input: unknown) => SwingyDataParts[keyof SwingyDataParts]
}

export const TOOL_DATA_MAP: Record<string, ToolDataMapping> = {
  get_prices: {
    partType: 'price-chart',
    transform: (output, input) => {
      const resp = output as ChartHistoryResponse
      const inp = input as { ticker: string }
      return { ticker: inp.ticker?.toUpperCase() ?? resp.symbol, candles: resp.data ?? [] }
    },
  },
  get_portfolio: {
    partType: 'portfolio-table',
    transform: (output) => output as unknown[],
  },
  get_trades: {
    partType: 'trades-table',
    transform: (output) => output as unknown[],
  },
  get_watchlist: {
    partType: 'watchlist-table',
    transform: (output) => output as unknown[],
  },
  get_alerts: {
    partType: 'alerts-card',
    transform: (output) => output as unknown[],
  },
  get_market_context: {
    partType: 'market-context',
    transform: (output) => output,
  },
}
