import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from 'recharts'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from './ui/dialog'

interface BetaDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tickerBetas: Record<string, number>
  portfolioBeta: number | null
}

const betaColor = (beta: number) => {
  if (beta > 1.2) return '#f59e0b' // amber — aggressive
  if (beta < 0.8) return '#38bdf8' // sky — defensive
  return '#a1a1aa' // zinc — neutral
}

export function BetaDialog({
  open,
  onOpenChange,
  tickerBetas,
  portfolioBeta,
}: BetaDialogProps) {
  const data = Object.entries(tickerBetas)
    .map(([ticker, beta]) => ({ ticker, beta }))
    .sort((a, b) => b.beta - a.beta)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Stock Betas vs VN-Index</DialogTitle>
          <DialogDescription>
            Sensitivity of each holding to VN-Index movements (90-day rolling)
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {data.length > 0 ? (
            <ResponsiveContainer width="100%" height={Math.max(200, data.length * 36 + 40)}>
              <BarChart
                data={data}
                layout="vertical"
                margin={{ top: 5, right: 30, bottom: 5, left: 50 }}
              >
                <CartesianGrid
                  horizontal={false}
                  strokeDasharray="3 3"
                  stroke="hsl(var(--border))"
                  opacity={0.5}
                />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  stroke="hsl(var(--border))"
                  domain={[0, 'auto']}
                />
                <YAxis
                  type="category"
                  dataKey="ticker"
                  width={48}
                  tick={{ fontSize: 12, fill: '#fafafa', fontFamily: 'var(--font-geist-mono)' }}
                  stroke="hsl(var(--border))"
                />
                <Tooltip
                  cursor={false}
                  wrapperStyle={{ zIndex: 50 }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const d = payload[0].payload as { ticker: string; beta: number }
                    const label =
                      d.beta > 1.2 ? 'Aggressive' : d.beta < 0.8 ? 'Defensive' : 'Market-aligned'
                    return (
                      <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded-lg px-3 py-2 shadow-xl text-sm">
                        <span className="font-semibold">{d.ticker}</span>
                        <span className="text-muted-foreground ml-2">Beta:</span>
                        <span className="font-mono ml-1" style={{ color: betaColor(d.beta) }}>
                          {d.beta.toFixed(2)}
                        </span>
                        <span className="text-muted-foreground ml-2 text-xs">({label})</span>
                      </div>
                    )
                  }}
                />
                <ReferenceLine
                  x={1}
                  stroke="hsl(var(--muted-foreground))"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={{
                    value: 'β=1',
                    position: 'top',
                    style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))' },
                  }}
                />
                <Bar dataKey="beta" radius={[0, 4, 4, 0]} maxBarSize={24}>
                  {data.map((entry) => (
                    <Cell key={entry.ticker} fill={betaColor(entry.beta)} fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted-foreground text-sm text-center py-8">
              No per-ticker beta data available
            </p>
          )}

          {portfolioBeta !== null && (
            <p className="text-xs text-muted-foreground text-center font-mono tabular-nums">
              Portfolio Beta: {portfolioBeta.toFixed(2)}
            </p>
          )}

          <div className="text-xs text-muted-foreground space-y-1 px-2">
            <p>
              <span style={{ color: '#f59e0b' }} className="font-medium">Beta &gt; 1.2</span> — stock amplifies market moves (aggressive).{' '}
              <span style={{ color: '#38bdf8' }} className="font-medium">Beta &lt; 0.8</span> — stock dampens market moves (defensive).
            </p>
            <p>Use higher-beta stocks for momentum trades and lower-beta for capital preservation.</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
