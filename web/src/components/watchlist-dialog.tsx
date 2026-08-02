import { useState, useEffect } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Textarea } from './ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { FieldError } from './ui/field-error'
import { Briefcase, ArrowLeftRight, TrendingDown } from 'lucide-react'
import { cn } from '../lib/utils'
import { formatPriceVnd } from '../lib/watchlist-utils'
import { useAddToWatchlist, useSectors, useUnifiedWatchlist, usePortfolioHoldings } from '../hooks/use-watchlist'
import { useCurrentPrices } from '../hooks/use-sparkline-data'
import type { StockType, ConvictionLevel, WatchlistAddInput } from '../types/index'

interface WatchlistDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultTicker?: string
}

const STOCK_TYPES: StockType[] = [
  'Private', 'State', 'Industrial', 'Vingroup', 'Retail', 'Securities',
  'Conglomerate', 'Energy', 'Commodities', 'Aviation', 'Insurance',
  'Beverages', 'Dairy', 'Logistics', 'Steel',
]
const CONVICTIONS: ConvictionLevel[] = ['High', 'Medium-High', 'Medium', 'Medium-Low', 'Low']

const watchlistSchema = z.object({
  ticker: z.string().min(1, 'Required').max(10, 'Max 10 chars'),
  sector_name: z.string().min(1, 'Required'),
  stock_type: z.string().optional(),
  is_pinned: z.boolean().default(false),
  pin_reason: z.string().optional(),
  entry_zone_vnd: z.coerce.number().min(1).optional().or(z.literal('')).or(z.nan()),
  conviction: z.string().optional(),
  tier: z.coerce.number().min(1).max(3).optional().or(z.literal('')).or(z.nan()),
  notes: z.string().optional(),
})
type WatchlistFormData = z.infer<typeof watchlistSchema>

const DEFAULTS: WatchlistFormData = {
  ticker: '', sector_name: '', stock_type: 'Private',
  is_pinned: false, pin_reason: '',
  entry_zone_vnd: '' as unknown as number, conviction: 'Medium',
  tier: '' as unknown as number, notes: '',
}

export function WatchlistDialog({ open, onOpenChange, defaultTicker }: WatchlistDialogProps) {
  const [planType, setPlanType] = useState<'swing' | 'longterm'>('swing')
  const addToWatchlist = useAddToWatchlist()
  const { data: sectors } = useSectors()
  const { items: unifiedItems } = useUnifiedWatchlist()
  const { data: holdingsMap } = usePortfolioHoldings()
  const isSwing = planType === 'swing'
  const { register, handleSubmit, control, watch, reset, formState: { errors } } = useForm<WatchlistFormData>({
    resolver: zodResolver(watchlistSchema),
    defaultValues: { ...DEFAULTS, ticker: defaultTicker?.toUpperCase() ?? '' },
  })

  const tickerValue = watch('ticker')?.toUpperCase()
  const showContext = tickerValue && tickerValue.length >= 3
  const { data: priceMap } = useCurrentPrices(showContext ? [tickerValue] : [])
  const currentPrice = showContext ? priceMap?.get(tickerValue) : undefined
  const existingItem = showContext ? unifiedItems?.find((item) => item.ticker === tickerValue) : undefined
  const heldShares = showContext ? holdingsMap?.get(tickerValue) : undefined

  useEffect(() => {
    if (open) { reset({ ...DEFAULTS, ticker: defaultTicker?.toUpperCase() ?? '' }); setPlanType('swing') }
  }, [open, reset, defaultTicker])

  const onSubmit = async (data: WatchlistFormData) => {
    const input: WatchlistAddInput = {
      ticker: data.ticker.toUpperCase(), type: planType,
      sector_name: data.sector_name, notes: data.notes || undefined,
    }
    if (isSwing) {
      input.stock_type = (data.stock_type as StockType) || 'Private'
      input.is_pinned = data.is_pinned
      input.pin_reason = data.is_pinned ? data.pin_reason : undefined
    } else {
      const entryZone = Number(data.entry_zone_vnd)
      input.entry_zone_vnd = !isNaN(entryZone) && entryZone > 0 ? entryZone : undefined
      input.conviction = (data.conviction as ConvictionLevel) || 'Medium'
      const tierValue = Number(data.tier)
      input.tier = !isNaN(tierValue) && tierValue >= 1 ? tierValue : undefined
    }
    try {
      await addToWatchlist.mutateAsync(input)
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to add to watchlist:', error)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-test-id="watchlist-dialog">
        <DialogHeader>
          <DialogTitle>Add to Watchlist</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Plan type toggle */}
          <div className="flex gap-1 p-0.5 bg-muted/40 rounded-md w-fit">
            {(['swing', 'longterm'] as const).map((plan) => (
              <button key={plan} type="button" onClick={() => setPlanType(plan)} className={cn(
                'px-3 py-1 rounded text-xs font-medium transition-colors cursor-pointer',
                planType === plan ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
              )}>
                {plan === 'swing' ? 'Swing' : 'Long-Term'}
              </button>
            ))}
          </div>

          {/* Ticker + Sector */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="wl-ticker">Ticker <span className="text-destructive">*</span></Label>
              <Input id="wl-ticker" data-test-id="wl-ticker" placeholder="TCB" maxLength={10}
                {...register('ticker', { onChange: (e) => { e.target.value = e.target.value.toUpperCase() } })} />
              <FieldError message={errors.ticker?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="wl-sector">Sector <span className="text-destructive">*</span></Label>
              <Controller name="sector_name" control={control} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="wl-sector" data-test-id="wl-sector" className="w-full">
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(sectors ?? []).map((sector) => (
                      <SelectItem key={sector.name} value={sector.name}>{sector.display_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
              <FieldError message={errors.sector_name?.message} />
            </div>
          </div>

          {/* Context panel */}
          {showContext && (currentPrice != null || existingItem || heldShares != null) && (
            <div className="flex flex-wrap gap-2 rounded-md bg-muted/30 px-3 py-2">
              {currentPrice != null && (
                <Badge variant="outline" className="text-xs gap-1">
                  <TrendingDown className="h-3 w-3" />{formatPriceVnd(currentPrice)} VND
                </Badge>
              )}
              {existingItem && (
                <Badge variant="outline" className="text-xs gap-1 text-amber-400 border-amber-500/30">
                  <ArrowLeftRight className="h-3 w-3" />
                  Already on: {existingItem.plans.map((p) => p === 'swing' ? 'Swing' : 'LT').join(' + ')}
                </Badge>
              )}
              {heldShares != null && (
                <Badge variant="outline" className="text-xs gap-1 text-emerald-400 border-emerald-500/30">
                  <Briefcase className="h-3 w-3" />Held {heldShares.toLocaleString()} shares
                </Badge>
              )}
            </div>
          )}

          {/* Plan-specific fields */}
          {!isSwing && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="wl-entry-zone">Entry Zone (VND)</Label>
                  <Input id="wl-entry-zone" type="number" {...register('entry_zone_vnd')} placeholder="35000" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wl-tier">Tier</Label>
                  <Controller name="tier" control={control} render={({ field }) => (
                    <Select value={field.value ? String(field.value) : ''}
                      onValueChange={(v) => field.onChange(v ? Number(v) : '')}>
                      <SelectTrigger id="wl-tier" className="w-full"><SelectValue placeholder="Select..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">1 -- Core</SelectItem>
                        <SelectItem value="2">2 -- Growth</SelectItem>
                        <SelectItem value="3">3 -- Speculative</SelectItem>
                      </SelectContent>
                    </Select>
                  )} />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="wl-conviction">Conviction</Label>
                <Controller name="conviction" control={control} render={({ field }) => (
                  <Select value={field.value ?? 'Medium'} onValueChange={field.onChange}>
                    <SelectTrigger id="wl-conviction" className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CONVICTIONS.map((level) => <SelectItem key={level} value={level}>{level}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )} />
              </div>
            </>
          )}

          <div className="space-y-2">
            <Label htmlFor="wl-notes">Notes</Label>
            <Textarea id="wl-notes" {...register('notes')} placeholder="Optional notes..." rows={2} />
          </div>

          {isSwing && (
            <>
              <div className="flex items-center gap-3">
                <input type="checkbox" id="wl-pinned" {...register('is_pinned')}
                  className="size-4 rounded border-input accent-primary cursor-pointer" />
                <Label htmlFor="wl-pinned" className="cursor-pointer text-xs">Pin this stock</Label>
              </div>
              {watch('is_pinned') && (
                <div className="space-y-2">
                  <Label htmlFor="wl-pin-reason" className="text-xs">Pin Reason</Label>
                  <Input id="wl-pin-reason" {...register('pin_reason')} placeholder="Why pin this?" />
                </div>
              )}
            </>
          )}
          {isSwing && (
            <div className="space-y-2">
              <Label htmlFor="wl-stock-type" className="text-xs text-muted-foreground">Stock Type (optional)</Label>
              <Controller name="stock_type" control={control} render={({ field }) => (
                <Select value={field.value ?? ''} onValueChange={field.onChange}>
                  <SelectTrigger id="wl-stock-type" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STOCK_TYPES.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}
                  </SelectContent>
                </Select>
              )} />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}
              disabled={addToWatchlist.isPending}>Cancel</Button>
            <Button type="submit" data-test-id="wl-save" disabled={addToWatchlist.isPending}>
              {addToWatchlist.isPending ? 'Adding...' : 'Add to ' + (isSwing ? 'Swing' : 'Long-Term')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
