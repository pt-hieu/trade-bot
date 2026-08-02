import { useEffect, useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { tradeSchema } from './trade-form-schema'
import type { TradeFormData } from './trade-form-schema'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from '../ui/sheet'
import { Button } from '../ui/button'
import { TradeFormFields } from './trade-form-fields'
import { useCreateTrade, useUpdateTrade } from '../../hooks/use-trades'
import { formatDateForInput } from '../../lib/date'
import type { Trade, TradeInput } from '../../types/index'
import type { TickerTradeGroup } from '../../lib/trade-grouping'

interface TradeSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  trade?: Trade
  initialStatus?: 'OPEN' | 'CLOSED'
  tickerGroups?: TickerTradeGroup[]
  currentPrices?: Map<string, number>
}

export function TradeSheet({
  open,
  onOpenChange,
  trade,
  initialStatus,
  tickerGroups,
  currentPrices,
}: TradeSheetProps) {
  const createTrade = useCreateTrade()
  const updateTrade = useUpdateTrade()
  const isEditing = !!trade

  const form = useForm<TradeFormData>({
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

  const { watch, reset, setValue, handleSubmit } = form
  const status = watch('status')
  const shares = watch('shares')
  const tickerValue = watch('ticker')
  const exitPriceVnd = watch('exit_price_vnd')
  const entryPriceVnd = watch('entry_price_vnd')

  // Auto-fill exit_shares when creating new closed trade
  useEffect(() => {
    if (!isEditing && status === 'CLOSED' && shares) {
      setValue('exit_shares', shares)
    }
  }, [isEditing, status, shares, setValue])

  useEffect(() => {
    if (open && trade) {
      reset({
        ticker: trade.ticker,
        entry_date: formatDateForInput(trade.entry_date) || '',
        entry_price_vnd: trade.entry_price_vnd,
        shares: trade.shares,
        strategy: trade.strategy,
        plan_type: trade.plan_type,
        status: initialStatus ?? trade.status,
        exit_date:
          formatDateForInput(trade.exit_date) ||
          (initialStatus === 'CLOSED' ? new Date().toISOString().split('T')[0] : null),
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
  }, [open, trade, reset, initialStatus])

  // Ticker context
  const tickerContext = useMemo(() => {
    if (!tickerValue || !tickerGroups) return null
    const normalized = tickerValue.toUpperCase()
    return tickerGroups.find((group) => group.ticker === normalized) || null
  }, [tickerValue, tickerGroups])

  const currentPrice = useMemo(() => {
    if (!tickerValue || !currentPrices) return null
    return currentPrices.get(tickerValue.toUpperCase()) || null
  }, [tickerValue, currentPrices])

  // P/L preview for close flow
  const plPreview = useMemo(() => {
    if (status !== 'CLOSED' || !exitPriceVnd || !entryPriceVnd || !shares) return null
    const exitPrice = Number(exitPriceVnd)
    const entryPrice = Number(entryPriceVnd)
    const shareCount = Number(shares)
    if (!exitPrice || !entryPrice || !shareCount) return null
    const grossProfitLoss = (exitPrice - entryPrice) * shareCount
    const percentChange = entryPrice > 0 ? ((exitPrice - entryPrice) / entryPrice) * 100 : 0
    return { grossProfitLoss, percentChange }
  }, [status, exitPriceVnd, entryPriceVnd, shares])

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
        data.status === 'CLOSED' && data.exit_price_vnd ? Number(data.exit_price_vnd) : null,
      exit_shares:
        data.status === 'CLOSED' && data.exit_shares ? Number(data.exit_shares) : undefined,
    }

    try {
      if (isEditing) {
        await updateTrade.mutateAsync({ id: trade.id, input })
      } else {
        await createTrade.mutateAsync(input)
      }
      onOpenChange(false)
    } catch (submitError) {
      console.error('Failed to save trade:', submitError)
    }
  }

  const isPending = createTrade.isPending || updateTrade.isPending

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{isEditing ? 'Edit Trade' : 'New Trade'}</SheetTitle>
          {isEditing && (
            <SheetDescription>
              Entry fields locked. Delete and recreate to fix errors.
            </SheetDescription>
          )}
        </SheetHeader>

        <SheetBody>
          <form id="trade-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <TradeFormFields
              form={form}
              isEditing={isEditing}
              trade={trade}
              plPreview={plPreview}
              tickerContext={tickerContext}
              currentPrice={currentPrice}
            />
          </form>
        </SheetBody>

        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" form="trade-form" disabled={isPending}>
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
