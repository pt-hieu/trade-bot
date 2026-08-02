import { PriceChartRenderer } from './price-chart'
import { PortfolioTableRenderer } from './portfolio-table'
import type { SwingyDataParts } from '../../../lib/chat/data-parts'

interface DataPartRendererProps {
  part: { type: string; data: unknown }
}

/**
 * Routes data-* parts to their React renderer components.
 * Returns null for unknown part types — graceful fallback.
 */
export function DataPartRenderer({ part }: DataPartRendererProps) {
  switch (part.type as `data-${keyof SwingyDataParts}`) {
    case 'data-price-chart':
      return <PriceChartRenderer data={part.data as SwingyDataParts['price-chart']} />

    case 'data-portfolio-table':
      return <PortfolioTableRenderer data={part.data as unknown[]} />

    // Remaining renderers — future work
    case 'data-trades-table':
    case 'data-watchlist-table':
    case 'data-alerts-card':
    case 'data-market-context':
      return null

    default:
      return null
  }
}
