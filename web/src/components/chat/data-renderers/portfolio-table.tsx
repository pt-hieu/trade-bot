import { cn } from '../../../lib/utils'

interface PortfolioRow {
  ticker: string
  shares: number
  avg_cost_vnd: number
  current_price_vnd: number
  market_value_vnd: number
  pl_vnd: number
  pl_pct: number
  sector_name?: string
}

interface PortfolioTableRendererProps {
  data: unknown[]
}

export function PortfolioTableRenderer({ data }: PortfolioTableRendererProps) {
  const rows = data as PortfolioRow[]
  if (!rows?.length) return null

  const totalValue = rows.reduce((s, r) => s + (Number(r.market_value_vnd) || 0), 0)
  const totalPl = rows.reduce((s, r) => s + (Number(r.pl_vnd) || 0), 0)

  function fmt(n: number) {
    const v = Number(n)
    if (!isFinite(v)) return '—'
    const abs = Math.abs(v)
    if (abs >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
    if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
    return `${(v / 1_000).toFixed(0)}K`
  }

  function fmtPrice(n: unknown) {
    const v = Number(n)
    if (!v || !isFinite(v)) return '—'
    return v.toFixed(1)
  }

  return (
    <div className="rounded border border-border/20 overflow-hidden my-1">
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/20">
        <span className="text-[10px] font-mono text-foreground/50 tracking-wider">
          PORTFOLIO
        </span>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-muted-foreground/40">
            {fmt(totalValue)} VND
          </span>
          <span
            className={cn(
              'text-[10px] font-mono tabular-nums',
              totalPl >= 0 ? 'text-emerald-400/70' : 'text-rose-400/70',
            )}
          >
            {totalPl >= 0 ? '+' : ''}{fmt(totalPl)}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="border-b border-border/20">
              {['Ticker', 'Shares', 'Avg', 'Price', 'Value', 'P&L', '%'].map((h) => (
                <th
                  key={h}
                  className="px-2 py-1 text-left text-muted-foreground/40 font-normal"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pl = Number(r.pl_vnd) || 0
              const isUp = pl >= 0
              return (
                <tr key={r.ticker} className="border-b border-border/10 last:border-0">
                  <td className="px-2 py-1 text-foreground/70 font-semibold">{r.ticker}</td>
                  <td className="px-2 py-1 text-foreground/50 tabular-nums">{r.shares}</td>
                  <td className="px-2 py-1 text-foreground/40 tabular-nums">
                    {Number(r.avg_cost_vnd).toFixed(1)}
                  </td>
                  <td className="px-2 py-1 text-foreground/60 tabular-nums">
                    {fmtPrice(r.current_price_vnd)}
                  </td>
                  <td className="px-2 py-1 text-foreground/50 tabular-nums">
                    {fmt(r.market_value_vnd)}
                  </td>
                  <td
                    className={cn(
                      'px-2 py-1 tabular-nums',
                      isUp ? 'text-emerald-400/70' : 'text-rose-400/70',
                    )}
                  >
                    {isUp ? '+' : ''}{fmt(pl)}
                  </td>
                  <td
                    className={cn(
                      'px-2 py-1 tabular-nums',
                      isUp ? 'text-emerald-400/70' : 'text-rose-400/70',
                    )}
                  >
                    {r.pl_pct != null ? `${isUp ? '+' : ''}${Number(r.pl_pct).toFixed(1)}%` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
