import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { ShieldAlert } from 'lucide-react'
import { formatShortDate } from '../../lib/date'
import type { TradingRule } from '../../types/index'

export function RulesCard({ data }: { data: TradingRule[] }) {
  if (!data.length) return null

  return (
    <Card className="border-border/50 p-4 space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-rose-400/80" />
          <h3 className="text-sm font-medium">Active rules</h3>
        </div>
        <span className="text-[10px] font-mono text-muted-foreground">
          {data.length} active
        </span>
      </div>

      <div className="overflow-x-auto -mx-4 px-4">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/30 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
              <th className="text-left pb-2 pr-3 font-medium">Rule</th>
              <th className="text-right pb-2 px-2 font-medium whitespace-nowrap">Conf</th>
              <th className="text-right pb-2 px-2 font-medium">n</th>
              <th className="text-right pb-2 pl-2 font-medium">Expires</th>
            </tr>
          </thead>
          <tbody>
            {data.map((rule) => (
              <tr key={rule.rule_name} className="border-b border-border/15 last:border-0">
                <td className="py-2 pr-3 text-foreground/90 leading-snug">{rule.description}</td>
                <td className="py-2 px-2 text-right align-top whitespace-nowrap">
                  {rule.confidence != null && (
                    <Badge variant="outline" className="text-[10px] border-rose-500/30 text-rose-400">
                      {(Number(rule.confidence) * 100).toFixed(0)}%
                    </Badge>
                  )}
                </td>
                <td className="py-2 px-2 text-right align-top font-mono text-muted-foreground/60 tabular-nums">
                  {rule.sample_size ?? '—'}
                </td>
                <td className="py-2 pl-2 text-right align-top text-muted-foreground/40 whitespace-nowrap">
                  {rule.expires_at ? formatShortDate(rule.expires_at) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
