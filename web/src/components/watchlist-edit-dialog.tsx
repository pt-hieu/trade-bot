import { useEffect } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Textarea } from './ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { useEditWatchlistItem } from '../hooks/use-watchlist'
import type {
  SwingWatchlistItem,
  LongtermWatchlistItem,
  StockType,
  ConvictionLevel,
  WatchlistEditInput,
} from '../types/index'

const STOCK_TYPES: StockType[] = [
  'Private', 'State', 'Industrial', 'Vingroup', 'Retail',
  'Securities', 'Conglomerate', 'Energy', 'Commodities',
  'Aviation', 'Insurance', 'Beverages', 'Dairy', 'Logistics', 'Steel',
]

const CONVICTIONS: ConvictionLevel[] = [
  'High', 'Medium-High', 'Medium', 'Medium-Low', 'Low',
]

const editSchema = z.object({
  stock_type: z.string().optional(),
  is_pinned: z.boolean().default(false),
  pin_reason: z.string().optional(),
  conviction: z.string().optional(),
  tier: z.coerce.number().min(1).max(3).optional().or(z.literal('')).or(z.nan()),
  entry_zone_vnd: z.coerce.number().min(1).optional().or(z.literal('')).or(z.nan()),
  notes: z.string().optional(),
})

type EditFormData = z.infer<typeof editSchema>

interface WatchlistEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  item: SwingWatchlistItem | LongtermWatchlistItem | null
  type: 'swing' | 'longterm'
}

export function WatchlistEditDialog({ open, onOpenChange, item, type }: WatchlistEditDialogProps) {
  const editMutation = useEditWatchlistItem()
  const isSwing = type === 'swing'

  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
  } = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      stock_type: 'Private',
      is_pinned: false,
      pin_reason: '',
      conviction: 'Medium',
      tier: '' as unknown as number,
      entry_zone_vnd: '' as unknown as number,
      notes: '',
    },
  })

  const isPinned = watch('is_pinned')

  useEffect(() => {
    if (open && item) {
      if (isSwing) {
        const s = item as SwingWatchlistItem
        reset({
          stock_type: s.stock_type ?? 'Private',
          is_pinned: s.is_pinned,
          pin_reason: s.pin_reason ?? '',
          notes: s.notes ?? '',
        })
      } else {
        const l = item as LongtermWatchlistItem
        reset({
          conviction: l.conviction ?? 'Medium',
          tier: l.tier ?? ('' as unknown as number),
          entry_zone_vnd: l.entry_zone_vnd ?? ('' as unknown as number),
          notes: l.notes ?? '',
        })
      }
    }
  }, [open, item, isSwing, reset])

  const onSubmit = async (data: EditFormData) => {
    if (!item) return

    const input: WatchlistEditInput = {
      ticker: item.ticker,
      type,
      notes: data.notes || null,
    }

    if (isSwing) {
      input.stock_type = (data.stock_type as StockType) || undefined
      input.is_pinned = data.is_pinned
      input.pin_reason = data.is_pinned ? (data.pin_reason || null) : null
    } else {
      input.conviction = (data.conviction as ConvictionLevel) || undefined
      const t = Number(data.tier)
      input.tier = !isNaN(t) && t >= 1 ? t : undefined
      const ez = Number(data.entry_zone_vnd)
      input.entry_zone_vnd = !isNaN(ez) && ez > 0 ? ez : undefined
    }

    try {
      await editMutation.mutateAsync(input)
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to edit watchlist item:', error)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-test-id="watchlist-edit-dialog">
        <DialogHeader>
          <DialogTitle>
            Edit {item?.ticker}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {isSwing && (
            <>
              <div className="space-y-2">
                <Label htmlFor="edit-stock-type">Stock Type</Label>
                <Controller
                  name="stock_type"
                  control={control}
                  render={({ field }) => (
                    <Select value={field.value ?? ''} onValueChange={field.onChange}>
                      <SelectTrigger id="edit-stock-type" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {STOCK_TYPES.map((t) => (
                          <SelectItem key={t} value={t}>{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="edit-pinned"
                  {...register('is_pinned')}
                  className="size-4 rounded border-input accent-primary cursor-pointer"
                />
                <Label htmlFor="edit-pinned" className="cursor-pointer">
                  Pin this stock
                </Label>
              </div>

              {isPinned && (
                <div className="space-y-2">
                  <Label htmlFor="edit-pin-reason">Pin Reason</Label>
                  <Input
                    id="edit-pin-reason"
                    {...register('pin_reason')}
                    placeholder="Why is this pinned?"
                  />
                </div>
              )}
            </>
          )}

          {!isSwing && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-entry-zone">Entry Zone (VND)</Label>
                  <Input
                    id="edit-entry-zone"
                    type="number"
                    {...register('entry_zone_vnd')}
                    placeholder="35000"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-tier">Tier</Label>
                  <Controller
                    name="tier"
                    control={control}
                    render={({ field }) => (
                      <Select
                        value={field.value ? String(field.value) : ''}
                        onValueChange={(v) => field.onChange(v ? Number(v) : '')}
                      >
                        <SelectTrigger id="edit-tier" className="w-full">
                          <SelectValue placeholder="Select..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">1 — Core</SelectItem>
                          <SelectItem value="2">2 — Growth</SelectItem>
                          <SelectItem value="3">3 — Speculative</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-conviction">Conviction</Label>
                <Controller
                  name="conviction"
                  control={control}
                  render={({ field }) => (
                    <Select value={field.value ?? 'Medium'} onValueChange={field.onChange}>
                      <SelectTrigger id="edit-conviction" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CONVICTIONS.map((c) => (
                          <SelectItem key={c} value={c}>{c}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
            </>
          )}

          <div className="space-y-2">
            <Label htmlFor="edit-notes">Notes</Label>
            <Textarea
              id="edit-notes"
              {...register('notes')}
              placeholder="Optional notes..."
              rows={2}
            />
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={editMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              data-test-id="wl-edit-save"
              disabled={editMutation.isPending}
            >
              {editMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
