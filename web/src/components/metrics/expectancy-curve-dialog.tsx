import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot } from 'recharts'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog'
import { formatCompact } from '../../lib/utils'

interface ExpectancyCurveDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  winRate: number
  winLossRatio: number
  expectancyVnd: number
}

const EXPECTANCY_CURVE_DATA = Array.from({ length: 81 }, (_, i) => {
  const winPct = i + 10
  const winRate = winPct / 100
  return { winPct, breakevenRatio: Math.min((1 - winRate) / winRate, 10) }
})

export function ExpectancyCurveDialog({ open, onOpenChange, winRate, winLossRatio, expectancyVnd }: ExpectancyCurveDialogProps) {
  const isProfitable = winLossRatio > (1 - winRate / 100) / (winRate / 100)
  const dotColor = isProfitable ? '#10b981' : '#f43f5e'
  const yMax = Math.max(6, Math.ceil(winLossRatio) + 1)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Expectancy Curve</DialogTitle>
          <DialogDescription>
            Your trading system relative to the breakeven line
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center gap-4 py-4">
          <AreaChart
            width={420}
            height={280}
            data={EXPECTANCY_CURVE_DATA}
            margin={{ top: 10, right: 20, bottom: 5, left: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="winPct"
              type="number"
              domain={[10, 90]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
              stroke="hsl(var(--border))"
            />
            <YAxis
              domain={[0, yMax]}
              tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
              stroke="hsl(var(--border))"
              label={{
                value: 'W/L Ratio',
                angle: -90,
                position: 'insideLeft',
                style: { fontSize: 11, fill: 'hsl(var(--muted-foreground))' },
              }}
            />
            <Tooltip
              wrapperStyle={{ zIndex: 50 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload
                return (
                  <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded-lg px-3 py-2 shadow-xl text-sm">
                    <span className="text-muted-foreground">Win Rate:</span>
                    <span className="font-mono ml-1">{d.winPct}%</span>
                    <span className="text-muted-foreground ml-3">Breakeven W/L:</span>
                    <span className="font-mono ml-1">{d.breakevenRatio.toFixed(2)}</span>
                  </div>
                )
              }}
            />
            <Area
              type="monotone"
              dataKey="breakevenRatio"
              stroke="#f43f5e"
              strokeWidth={2}
              fill="#f43f5e"
              fillOpacity={0.08}
            />
            <ReferenceDot
              x={winRate}
              y={winLossRatio}
              r={7}
              fill={dotColor}
              stroke="white"
              strokeWidth={2}
            />
          </AreaChart>
          <div className="flex gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: dotColor }} />
              <span className="font-mono tabular-nums">
                {winRate}% · {winLossRatio.toFixed(2)} W/L
              </span>
            </div>
            <span className={`font-semibold ${isProfitable ? 'text-emerald-500' : 'text-rose-500'}`}>
              {isProfitable ? 'Profitable' : 'Unprofitable'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground font-mono tabular-nums">
            Expectancy: {Number(expectancyVnd) >= 0 ? '+' : ''}{formatCompact(expectancyVnd)} / trade
          </p>
          <div className="text-xs text-muted-foreground space-y-1 mt-2 px-2">
            <p>The <span className="text-rose-500 font-medium">red curve</span> is the breakeven line. Any system on this line makes exactly zero over time.</p>
            <p>Your dot <span className="font-medium">above</span> the curve means your wins are large enough relative to your losses to be profitable at your win rate.</p>
            <p><span className="font-medium">Higher win rate</span> = you can tolerate a lower W/L ratio. <span className="font-medium">Lower win rate</span> = you need bigger wins per trade.</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
