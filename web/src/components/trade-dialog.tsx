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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { useCreateTrade, useUpdateTrade } from '../hooks/use-trades'
import { toTitleCase } from '../lib/utils'
import { STRATEGIES, STRATEGY_DEFINITIONS } from '../lib/strategy'
import type { Strategy } from '../lib/strategy'
import type { Trade, TradeInput } from '../types/index'

interface TradeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  trade?: Trade
  /** Pre-select status when dialog opens (useful for quick-close shortcut) */
  initialStatus?: 'OPEN' | 'CLOSED'
}

const PLAN_TYPES = ['SWING', 'LONGTERM'] as const
const STATUSES = ['OPEN', 'CLOSED'] as const

const tradeSchema = z
  .object({
    ticker: z.string().min(1, 'Required').max(10, 'Max 10 chars'),
    entry_date: z.string().min(1, 'Required'),
    entry_price_vnd: z.coerce.number().min(1, 'Must be > 0'),
    shares: z.coerce.number().int('Must be whole number').min(1, 'Must be > 0'),
    strategy: z.enum(STRATEGIES).nullable(),
    plan_type: z.enum(PLAN_TYPES),
    status: z.enum(STATUSES),
    exit_date: z.string().nullable(),
    exit_price_vnd: z.coerce.number().min(1).nullable().or(z.literal('')),
    exit_shares: z.coerce.number().int().min(1).nullable().or(z.literal('')),
  })
  .refine((data) => data.status !== 'CLOSED' || data.exit_date, {
    message: 'Required when closed',
    path: ['exit_date'],
  })
  .refine(
    (data) =>
      data.status !== 'CLOSED' ||
      (data.exit_price_vnd !== null && data.exit_price_vnd !== ''),
    {
      message: 'Required when closed',
      path: ['exit_price_vnd'],
    }
  )
  .refine(
    (data) =>
      data.status !== 'CLOSED' ||
      (data.exit_shares !== null && data.exit_shares !== ''),
    {
      message: 'Required when closed',
      path: ['exit_shares'],
    }
  )

type TradeFormData = z.infer<typeof tradeSchema>

import { FieldError } from './ui/field-error'

export function TradeDialog({ open, onOpenChange, trade, initialStatus }: TradeDialogProps) {
  const createTrade = useCreateTrade()
  const updateTrade = useUpdateTrade()
  const isEditing = !!trade

  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
    setValue,
    formState: { errors },
  } = useForm<TradeFormData>({
    resolver: zodResolver(tradeSchema),
    defaultValues: {
      ticker: '',
      entry_date: new Date().toISOString().split('T')[0],
      entry_price_vnd: '' as unknown as number,
      shares: '' as unknown as number,
      strategy: null,
      plan_type: 'SWING',
      status: 'OPEN',
      exit_date: null,
      exit_price_vnd: null,
      exit_shares: null,
    },
  })

  const status = watch('status')
  const shares = watch('shares')
  const selectedStrategy = watch('strategy')

  // Sync exit_shares to shares when creating a new closed trade
  useEffect(() => {
    if (!isEditing && status === 'CLOSED' && shares) {
      setValue('exit_shares', shares)
    }
  }, [isEditing, status, shares, setValue])

  // Format date to YYYY-MM-DD for HTML date input
  const formatDateForInput = (date: string | Date | null): string | null => {
    if (!date) return null
    if (date instanceof Date) return date.toISOString().split('T')[0]
    return date.split('T')[0]
  }

  // Reset form when dialog opens/closes or trade changes
  useEffect(() => {
    if (open && trade) {
      reset({
        ticker: trade.ticker,
        entry_date: formatDateForInput(trade.entry_date) ?? '',
        entry_price_vnd: trade.entry_price_vnd,
        shares: trade.shares,
        strategy: trade.strategy,
        plan_type: trade.plan_type,
        status: initialStatus ?? trade.status,
        exit_date: formatDateForInput(trade.exit_date) ?? (initialStatus === 'CLOSED' ? new Date().toISOString().split('T')[0] : null),
        exit_price_vnd: trade.exit_price_vnd ?? null,
        exit_shares: trade.shares,
      })
    } else if (open) {
      reset({
        ticker: '',
        entry_date: new Date().toISOString().split('T')[0],
        entry_price_vnd: '' as unknown as number,
        shares: '' as unknown as number,
        strategy: null,
        plan_type: 'SWING',
        status: 'OPEN',
        exit_date: null,
        exit_price_vnd: null,
        exit_shares: null,
      })
    }
  }, [open, trade, reset])

  const onSubmit = async (data: TradeFormData) => {
    const input: TradeInput = {
      ticker: data.ticker.toUpperCase(),
      entry_date: data.entry_date,
      entry_price_vnd: data.entry_price_vnd,
      shares: data.shares,
      strategy: data.strategy,
      plan_type: data.plan_type,
      status: data.status,
      exit_date: data.status === 'CLOSED' ? data.exit_date : null,
      exit_price_vnd:
        data.status === 'CLOSED' && data.exit_price_vnd
          ? Number(data.exit_price_vnd)
          : null,
      exit_shares:
        data.status === 'CLOSED' && data.exit_shares
          ? Number(data.exit_shares)
          : undefined,
    }

    try {
      if (isEditing) {
        await updateTrade.mutateAsync({ id: trade.id, input })
      } else {
        await createTrade.mutateAsync(input)
      }
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to save trade:', error)
    }
  }

  const isPending = createTrade.isPending || updateTrade.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Trade' : 'New Trade'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="ticker">Ticker <span className="text-destructive">*</span></Label>
              <Input
                id="ticker"
                {...register('ticker', {
                  onChange: (e) => {
                    e.target.value = e.target.value.toUpperCase()
                  },
                })}
                placeholder="TCB"
                maxLength={10}
                disabled={isEditing}
              />
              <FieldError message={errors.ticker?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="planType">Plan</Label>
              <Controller
                name="plan_type"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange} disabled={isEditing}>
                    <SelectTrigger id="planType" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PLAN_TYPES.map((p) => (
                        <SelectItem key={p} value={p}>
                          {toTitleCase(p)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <FieldError message={errors.plan_type?.message} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="entryDate">Entry Date <span className="text-destructive">*</span></Label>
            <Input id="entryDate" type="date" {...register('entry_date')} disabled={isEditing} />
            <FieldError message={errors.entry_date?.message} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="entryPrice">Entry Price (VND) <span className="text-destructive">*</span></Label>
              <Input
                id="entryPrice"
                type="number"
                {...register('entry_price_vnd')}
                placeholder="35000"
                disabled={isEditing}
              />
              <FieldError message={errors.entry_price_vnd?.message} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="shares">Shares <span className="text-destructive">*</span></Label>
              <Input
                id="shares"
                type="number"
                {...register('shares')}
                placeholder="100"
                disabled={isEditing}
              />
              <FieldError message={errors.shares?.message} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="strategy">Strategy</Label>
              <Controller
                name="strategy"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value ?? ''}
                    onValueChange={(v) => field.onChange(v || null)}
                  >
                    <SelectTrigger id="strategy" className="w-full">
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                      {STRATEGIES.map((strategy) => (
                        <SelectItem key={strategy} value={strategy}>
                          <span>{strategy}</span>
                          <span className="block text-[10px] text-muted-foreground leading-tight">
                            {STRATEGY_DEFINITIONS[strategy]}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <FieldError message={errors.strategy?.message} />
              {selectedStrategy && (
                <p className="text-[11px] text-muted-foreground leading-snug">
                  {STRATEGY_DEFINITIONS[selectedStrategy as Strategy]}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="status">Status</Label>
              <Controller
                name="status"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="status" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STATUSES.map((s) => (
                        <SelectItem key={s} value={s}>
                          {toTitleCase(s)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <FieldError message={errors.status?.message} />
            </div>
          </div>

          {status === 'CLOSED' && (
            <div className="space-y-4 pt-2 border-t">
              <p className="text-sm text-muted-foreground">Exit Details</p>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="exitDate">Exit Date <span className="text-destructive">*</span></Label>
                  <Input
                    id="exitDate"
                    type="date"
                    {...register('exit_date')}
                  />
                  <FieldError message={errors.exit_date?.message} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="exitPrice">Exit Price (VND) <span className="text-destructive">*</span></Label>
                  <Input
                    id="exitPrice"
                    type="number"
                    {...register('exit_price_vnd')}
                    placeholder="38000"
                  />
                  <FieldError message={errors.exit_price_vnd?.message} />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="exitShares">
                  {isEditing && trade ? (
                    <>Shares to Close <span className="text-destructive">*</span>
                    <span className="text-muted-foreground font-normal ml-1">(of {trade.shares})</span></>
                  ) : (
                    <>Exit Shares <span className="text-destructive">*</span></>
                  )}
                </Label>
                <Input
                  id="exitShares"
                  type="number"
                  {...register('exit_shares')}
                  min={1}
                  max={isEditing && trade ? trade.shares : undefined}
                />
                <FieldError message={errors.exit_shares?.message} />
              </div>
            </div>
          )}

          {isEditing && (
            <p className="text-xs text-muted-foreground">
              Entry fields are locked. To fix errors, delete this trade and create a new one.
            </p>
          )}

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
