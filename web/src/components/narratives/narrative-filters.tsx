import { X } from 'lucide-react'
import { Input } from '../ui/input'
import { Badge } from '../ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { MATURITY_LABELS } from './narrative-utils'

interface NarrativeFiltersProps {
  tickerFilter: string
  onTickerFilterChange: (value: string) => void
  maturity: string
  onMaturityChange: (value: string) => void
  routeTickerFilter?: string
  onClearRouteTickerFilter?: () => void
}

export function NarrativeFilters({
  tickerFilter,
  onTickerFilterChange,
  maturity,
  onMaturityChange,
  routeTickerFilter,
  onClearRouteTickerFilter,
}: NarrativeFiltersProps) {
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      {routeTickerFilter && (
        <Badge variant="secondary" className="flex items-center gap-1 text-xs">
          Filtered: {routeTickerFilter}
          <button
            onClick={onClearRouteTickerFilter}
            className="ml-0.5 hover:text-foreground transition-colors cursor-pointer"
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      )}

      <Input
        placeholder="Filter by ticker..."
        value={tickerFilter}
        onChange={(event) => onTickerFilterChange(event.target.value)}
        className="h-8 w-[160px] text-xs font-mono"
      />

      <Select value={maturity} onValueChange={onMaturityChange}>
        <SelectTrigger className="w-[140px] h-8 text-xs">
          <SelectValue placeholder="Maturity" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Maturities</SelectItem>
          <SelectItem value="emerging">{MATURITY_LABELS.emerging}</SelectItem>
          <SelectItem value="developing">{MATURITY_LABELS.developing}</SelectItem>
          <SelectItem value="confirmed">{MATURITY_LABELS.confirmed}</SelectItem>
          <SelectItem value="mature">{MATURITY_LABELS.mature}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
