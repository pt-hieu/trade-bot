import { TrendingUp, TrendingDown } from 'lucide-react'
import { Badge } from '../ui/badge'
import { InsightToggle, InsightTrigger, InsightCard } from '../ui/detail-text'
import type { RotationData } from '../../types/index'

function formatSectorName(name: string) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

interface RotationSectionProps {
  rotation: RotationData
}

export function RotationSection({ rotation }: RotationSectionProps) {
  const hasData = rotation.hot_sectors.length > 0 || rotation.cold_sectors.length > 0

  return (
    <InsightToggle>
      <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-500" style={{ animationDelay: '120ms' }}>
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Sector Rotation</h2>
          {rotation.rotation_signal && <InsightTrigger />}
        </div>

        {!hasData ? (
          <p className="text-muted-foreground text-sm">No sector rotation detected for this session.</p>
        ) : (
          <div className="space-y-2">
            {rotation.hot_sectors.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold tracking-widest text-emerald-500 uppercase">HOT</span>
                {rotation.hot_sectors.map((s) => (
                  <Badge
                    key={s.sector_name}
                    className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 font-mono text-xs"
                  >
                    <TrendingUp className="mr-1 h-3 w-3" />
                    {formatSectorName(s.sector_name)}
                    {s.return_pct != null && (
                      <span className="ml-1 opacity-70">
                        +{Number(s.return_pct).toFixed(1)}%
                      </span>
                    )}
                  </Badge>
                ))}
              </div>
            )}

            {rotation.cold_sectors.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold tracking-widest text-rose-500 uppercase">COLD</span>
                {rotation.cold_sectors.map((s) => (
                  <Badge
                    key={s.sector_name}
                    className="bg-rose-500/15 text-rose-400 border-rose-500/20 font-mono text-xs"
                  >
                    <TrendingDown className="mr-1 h-3 w-3" />
                    {formatSectorName(s.sector_name)}
                    {s.return_pct != null && (
                      <span className="ml-1 opacity-70">
                        {Number(s.return_pct).toFixed(1)}%
                      </span>
                    )}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}

        {rotation.rotation_signal && (
          <InsightCard>{rotation.rotation_signal}</InsightCard>
        )}
      </div>
    </InsightToggle>
  )
}
