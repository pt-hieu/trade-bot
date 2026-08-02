import { Controller, type UseFormReturn } from 'react-hook-form'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import { FieldError } from '../ui/field-error'
import { TickerContextCard } from './ticker-context-card'
import { cn, toTitleCase, formatCompact, formatSignedCompact, formatPct, plColor } from '../../lib/utils'
import { STRATEGIES } from '../../lib/strategy'
import { PLAN_TYPES, STATUSES } from './trade-form-schema'
import type { TradeFormData } from './trade-form-schema'
import type { Trade } from '../../types/index'
import type { TickerTradeGroup } from '../../lib/trade-grouping'

interface TradeFormFieldsProps {
  form: UseFormReturn<TradeFormData>
  isEditing: boolean
  trade?: Trade
  plPreview: { grossProfitLoss: number; percentChange: number } | null
  /** Existing trade group for this ticker — surfaces position context */
  tickerContext: TickerTradeGroup | null
  /** Current market price for the ticker */
  currentPrice: number | null
}

export function TradeFormFields({
  form,
  isEditing,
  trade,
  plPreview,
  tickerContext,
  currentPrice,
}: TradeFormFieldsProps) {
  const {
    register,
    control,
    watch,
    formState: { errors },
  } = form

  const status = watch('status')
  const entryPriceVnd = watch('entry_price_vnd')

  return (
    <>
      {/* Ticker + Plan */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="ticker">
            Ticker <span className="text-destructive">*</span>
          </Label>
          <Input
            id="ticker"
            {...register('ticker', {
              onChange: (event) => {
                event.target.value = event.target.value.toUpperCase()
              },
            })}
            placeholder="TCB"
            maxLength={10}
            disabled={isEditing}
          />
          <FieldError message={errors.ticker?.message} />
        </div>
        <div className="space-y-1.5">
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
                  {PLAN_TYPES.map((planType) => (
                    <SelectItem key={planType} value={planType}>
                      {toTitleCase(planType)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
      </div>

      {/* Ticker context — surfaces immediately after typing ticker */}
      {tickerContext && (
        <TickerContextCard group={tickerContext} currentPrice={currentPrice} />
      )}

      {/* Entry date */}
      <div className="space-y-1.5">
        <Label htmlFor="entryDate">
          Entry Date <span className="text-destructive">*</span>
        </Label>
        <Input id="entryDate" type="date" {...register('entry_date')} disabled={isEditing} />
        <FieldError message={errors.entry_date?.message} />
      </div>

      {/* Entry price + Shares */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="entryPrice">
            Entry Price (VND) <span className="text-destructive">*</span>
          </Label>
          <Input
            id="entryPrice"
            type="number"
            {...register('entry_price_vnd')}
            placeholder="35000"
            disabled={isEditing}
          />
          <FieldError message={errors.entry_price_vnd?.message} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shares">
            Shares <span className="text-destructive">*</span>
          </Label>
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

      {/* Strategy + Status */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="strategy">Strategy</Label>
          <Controller
            name="strategy"
            control={control}
            render={({ field }) => (
              <Select
                value={field.value ?? ''}
                onValueChange={(value) => field.onChange(value || null)}
              >
                <SelectTrigger id="strategy" className="w-full">
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {STRATEGIES.map((strategy) => (
                    <SelectItem key={strategy} value={strategy}>
                      {strategy}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div className="space-y-1.5">
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
                  {STATUSES.map((statusOption) => (
                    <SelectItem key={statusOption} value={statusOption}>
                      {toTitleCase(statusOption)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
      </div>

      {/* Exit details — progressive disclosure */}
      {status === 'CLOSED' && (
        <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Exit details
          </p>

          {/* Reference prices — entry and current, so exit price has anchors */}
          <div className="flex items-center gap-4 text-xs rounded-md bg-muted/30 px-3 py-2">
            {entryPriceVnd ? (
              <div>
                <span className="text-muted-foreground">Entry</span>{' '}
                <span className="font-medium text-foreground">
                  {formatCompact(Number(entryPriceVnd))}
                </span>
              </div>
            ) : null}
            {currentPrice ? (
              <div>
                <span className="text-muted-foreground">Current</span>{' '}
                <span
                  className={cn(
                    'font-medium',
                    entryPriceVnd && currentPrice >= Number(entryPriceVnd)
                      ? 'text-emerald-400'
                      : entryPriceVnd
                        ? 'text-rose-400'
                        : 'text-foreground'
                  )}
                >
                  {formatCompact(currentPrice)}
                </span>
              </div>
            ) : null}
            {entryPriceVnd && currentPrice ? (
              <div
                className={cn(
                  'ml-auto font-medium',
                  currentPrice >= Number(entryPriceVnd) ? 'text-emerald-400' : 'text-rose-400'
                )}
              >
                {formatPct(
                  ((currentPrice - Number(entryPriceVnd)) / Number(entryPriceVnd)) * 100
                )}
              </div>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="exitDate">
                Exit Date <span className="text-destructive">*</span>
              </Label>
              <Input id="exitDate" type="date" {...register('exit_date')} />
              <FieldError message={errors.exit_date?.message} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exitPrice">
                Exit Price <span className="text-destructive">*</span>
              </Label>
              <Input
                id="exitPrice"
                type="number"
                {...register('exit_price_vnd')}
                placeholder={currentPrice ? String(currentPrice) : '38000'}
              />
              <FieldError message={errors.exit_price_vnd?.message} />
            </div>
          </div>
          {isEditing && trade && trade.shares > 1 && (
            <div className="space-y-1.5">
              <Label htmlFor="exitShares">
                Shares to Close <span className="text-destructive">*</span>
                <span className="text-muted-foreground font-normal ml-1">
                  (of {trade.shares})
                </span>
              </Label>
              <Input
                id="exitShares"
                type="number"
                {...register('exit_shares')}
                min={1}
                max={trade.shares}
              />
              <FieldError message={errors.exit_shares?.message} />
            </div>
          )}

          {/* Live P/L preview — verdict, not just numbers */}
          {plPreview && (
            <div
              className={cn(
                'rounded-md px-3 py-2 text-sm font-semibold',
                plPreview.grossProfitLoss >= 0
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : 'bg-rose-500/10 text-rose-400'
              )}
            >
              {plPreview.grossProfitLoss >= 0 ? 'Profit' : 'Loss'}:{' '}
              {formatSignedCompact(plPreview.grossProfitLoss)}{' '}
              ({formatPct(plPreview.percentChange)})
            </div>
          )}
        </div>
      )}
    </>
  )
}
