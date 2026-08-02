import { Link } from '@tanstack/react-router'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table'
import { Badge } from './ui/badge'
import { useTrades } from '../hooks/use-trades'
import { ErrorState } from './ui/error-state'
import type { Trade } from '../types/index'
import { formatVND, formatPct, plColor, toTitleCase } from '../lib/utils'
import { formatShortDate } from '../lib/date'

export function TradesTable() {
  const { data: trades, isLoading, error, refetch } = useTrades()

  if (isLoading) {
    return <div className="text-muted-foreground">Loading trades...</div>
  }

  if (error) {
    return <ErrorState description="Could not load recent trades." retry={refetch} />
  }

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">Recent Trades</h2>
        <Link
          to="/trades" search={{} as any}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          View all trades &rarr;
        </Link>
      </div>

      {!trades?.length ? (
        <div className="text-muted-foreground">No trades found</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticker</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead>Exit</TableHead>
                <TableHead className="text-right">Shares</TableHead>
                <TableHead className="text-right">P/L</TableHead>
                <TableHead className="text-right">P/L %</TableHead>
                <TableHead className="text-right">Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trades.map((trade) => (
                <TableRow key={trade.id}>
                  <TableCell className="font-medium">{trade.ticker}</TableCell>
                  <TableCell>{trade.strategy ?? '-'}</TableCell>
                  <TableCell>{trade.entry_date ? formatShortDate(trade.entry_date) : '-'}</TableCell>
                  <TableCell>{trade.exit_date ? formatShortDate(trade.exit_date) : '-'}</TableCell>
                  <TableCell className="text-right">{trade.shares}</TableCell>
                  <TableCell className={`text-right ${trade.status === 'OPEN' ? 'text-muted-foreground' : plColor(trade.pl_net_vnd)}`}>
                    {trade.status === 'OPEN' ? '-' : formatVND(trade.pl_net_vnd)}
                  </TableCell>
                  <TableCell className={`text-right ${trade.status === 'OPEN' ? 'text-muted-foreground' : plColor(trade.pl_pct)}`}>
                    {trade.status === 'OPEN' ? '-' : formatPct(trade.pl_pct)}
                  </TableCell>
                  <TableCell className="text-right">
                    {trade.status === 'CLOSED' ? (
                      <Badge
                        variant={trade.result === 'WIN' ? 'default' : 'destructive'}
                        className={trade.result === 'WIN' ? 'bg-green-600 hover:bg-green-600/90' : ''}
                      >
                        {toTitleCase(trade.result)}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">{toTitleCase(trade.status)}</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

    </>
  )
}
