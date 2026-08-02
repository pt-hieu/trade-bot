import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { CandlestickChart } from './candlestick-chart'
import { useAlerts } from '../../hooks/use-alerts'
import { useTrades } from '../../hooks/use-trades'
import { usePortfolio } from '../../hooks/use-portfolio'
import type { PriceMarker } from '../../types/chart'
import type { Alert } from '../../types/index'

interface ChartDialogProps {
  ticker: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function buildMarkers(
  ticker: string,
  alerts: Alert[] | undefined,
  trades: ReturnType<typeof useTrades>['data'],
  holdings: ReturnType<typeof usePortfolio>['data']
): PriceMarker[] {
  const markers: PriceMarker[] = []

  // Agent-recommended levels from active alerts (prices in raw VND → divide by 1000)
  const tickerAlerts = (alerts ?? []).filter((a) => a.ticker === ticker && a.status === 'active')
  for (const alert of tickerAlerts) {
    if (alert.entry_price) {
      markers.push({
        price: Number(alert.entry_price) / 1000,
        label: 'Entry',
        color: '#fbbf24',   // amber-400
        style: 'dashed',
      })
    }
    if (alert.stop_price) {
      markers.push({
        price: Number(alert.stop_price) / 1000,
        label: 'Stop',
        color: '#f43f5e',   // rose-500
        style: 'dashed',
      })
    }
    if (alert.target_price) {
      markers.push({
        price: Number(alert.target_price) / 1000,
        label: 'Target',
        color: '#10b981',   // emerald-500
        style: 'dashed',
      })
    }
  }

  // Actual entry price from open trades (prices in raw VND → divide by 1000)
  const openTrades = (trades ?? []).filter((t) => t.ticker === ticker && t.status === 'OPEN')
  for (const trade of openTrades) {
    if (trade.entry_price_vnd) {
      markers.push({
        price: Number(trade.entry_price_vnd) / 1000,
        label: 'Trade entry',
        color: '#60a5fa',   // blue-400
        style: 'solid',
      })
    }
  }

  // Average cost from portfolio holding (raw VND → divide by 1000)
  const holding = (holdings ?? []).find((h) => h.ticker === ticker)
  if (holding?.avg_cost_vnd) {
    markers.push({
      price: Number(holding.avg_cost_vnd) / 1000,
      label: 'Avg cost',
      color: '#71717a',   // zinc-500
      style: 'dotted',
    })
  }

  return markers
}

export function ChartDialog({ ticker, open, onOpenChange }: ChartDialogProps) {
  const { data: alertsRaw } = useAlerts('active')
  const { data: trades } = useTrades()
  const { data: holdings } = usePortfolio()

  const alerts = alertsRaw as Alert[] | undefined
  const markers = ticker ? buildMarkers(ticker, alerts, trades, holdings) : []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="w-[80vw] max-w-[80vw] sm:max-w-[80vw] h-[80vh] p-4 gap-3 flex flex-col"
        data-test-id="chart-dialog"
      >
        <DialogHeader className="pb-0 shrink-0">
          <DialogTitle className="font-mono text-base tracking-wider">
            {ticker ?? '—'}
          </DialogTitle>
        </DialogHeader>

        {ticker && (
          <CandlestickChart
            ticker={ticker}
            height={undefined}
            priceMarkers={markers}
            className="w-full flex-1 min-h-0"
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
