import { z } from 'zod'
import { STRATEGIES } from '../../lib/strategy'

const PLAN_TYPES = ['SWING', 'LONGTERM'] as const
const STATUSES = ['OPEN', 'CLOSED'] as const

export { PLAN_TYPES, STATUSES }

export const tradeSchema = z
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
    { message: 'Required when closed', path: ['exit_price_vnd'] }
  )
  .refine(
    (data) =>
      data.status !== 'CLOSED' ||
      (data.exit_shares !== null && data.exit_shares !== ''),
    { message: 'Required when closed', path: ['exit_shares'] }
  )

export type TradeFormData = z.infer<typeof tradeSchema>
