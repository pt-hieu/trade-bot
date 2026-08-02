import { PieChart, Pie, Cell, Tooltip } from 'recharts'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog'

interface WinRateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  wins: number
  losses: number
  winRate: number
}

export function WinRateDialog({ open, onOpenChange, wins, losses, winRate }: WinRateDialogProps) {
  const data = [
    { name: 'Wins', value: Number(wins), fill: '#10b981' },
    { name: 'Losses', value: Number(losses), fill: '#f43f5e' },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Win Rate</DialogTitle>
          <DialogDescription>Win/loss distribution across all closed trades</DialogDescription>
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
                      <span className="text-muted-foreground ml-2 font-mono">{d.value}</span>
                    </div>
                  )
                }}
              />
            </PieChart>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <p className="text-3xl font-bold font-mono tabular-nums">{winRate}%</p>
              <p className="text-xs text-muted-foreground">Win Rate</p>
            </div>
          </div>
          <div className="flex gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-emerald-500" />
              <span className="font-mono tabular-nums">{wins} Wins</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-rose-500" />
              <span className="font-mono tabular-nums">{losses} Losses</span>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
