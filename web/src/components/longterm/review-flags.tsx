const FLAG_CONFIG: Record<string, { label: string; color: string }> = {
  ROE_BELOW_8PCT_2Q: { label: 'Low ROE', color: 'bg-amber-500/15 text-amber-400' },
  HIGH_DEBT: { label: 'High Debt', color: 'bg-rose-500/15 text-rose-400' },
  'CONVICTION_DOWNGRADE_2+': { label: 'Conv. Drop', color: 'bg-rose-500/15 text-rose-400' },
  NO_FINANCIAL_DATA: { label: 'No Data', color: 'bg-zinc-500/15 text-zinc-400' },
  ENTRY_ZONE_DIVERGENCE_30PCT: { label: 'Zone Drift', color: 'bg-amber-500/15 text-amber-400' },
}

export function ReviewFlags({ flags }: { flags: string[] }) {
  if (!flags?.length) return null

  return (
    <div className="flex flex-wrap gap-1 mt-0.5">
      {flags.map((flag) => {
        const config = FLAG_CONFIG[flag]
        const label = config?.label ?? flag
        const color = config?.color ?? 'bg-zinc-500/15 text-zinc-400'
        return (
          <span
            key={flag}
            className={`inline-block rounded px-1 py-0 text-[10px] font-medium ${color}`}
          >
            {label}
          </span>
        )
      })}
    </div>
  )
}
