import { PieChart, Pie, Cell, Tooltip } from 'recharts'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog'
import { formatCompact } from '../../lib/utils'

interface ProfitFactorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  grossProfit: number
  grossLoss: number
  profitFactor: number
}

export function ProfitFactorDialog({ open, onOpenChange, grossProfit, grossLoss, profitFactor }: ProfitFactorDialogProps) {
  const data = [
    { name: 'Gross Profit', value: grossProfit, fill: '#10b981' },
    { name: 'Gross Loss', value: grossLoss, fill: '#f43f5e' },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Profit Factor</DialogTitle>
          <DialogDescription>Ratio of gross profits to gross losses</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center gap-4 py-4">
          <div className="relative" style={{ width: 256, height: 256 }}>
            <PieChart width={256} height={256}>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={110}
                startAngle={90}
                endAngle={-270}
                paddingAngle={2}
                strokeWidth={0}
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip
                wrapperStyle={{ zIndex: 50 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded-lg px-3 py-2 shadow-xl text-sm">
                      <span style={{ color: d.fill }} className="font-semibold">{d.name}</span>
                      <span className="text-muted-foreground ml-2 font-mono">{formatCompact(d.value)}</span>
                    </div>
                  )
                }}
              />
            </PieChart>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <p className="text-3xl font-bold font-mono tabular-nums">{profitFactor.toFixed(2)}</p>
              <p className="text-xs text-muted-foreground">Profit Factor</p>
            </div>
          </div>
          <div className="flex gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-emerald-500" />
              <span className="font-mono tabular-nums">+{formatCompact(grossProfit)}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-rose-500" />
              <span className="font-mono tabular-nums">-{formatCompact(grossLoss)}</span>
            </div>
          </div>
          <div className="text-xs text-muted-foreground space-y-1 mt-2 px-2">
            <p>Profit factor = <span className="font-medium">gross profits / gross losses</span>. It measures how many dollars you earn for every dollar you lose.</p>
            <p>A value <span className="text-emerald-500 font-medium">above 1.0</span> means you&apos;re making more than you lose. <span className="text-amber-500 font-medium">1.5+</span> is considered healthy for swing trading.</p>
            <p>Below <span className="text-rose-500 font-medium">1.0</span> means losses outweigh profits — review your stop-losses and targets.</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
