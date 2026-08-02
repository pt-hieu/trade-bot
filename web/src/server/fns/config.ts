import { createServerFn } from '@tanstack/react-start'
import { z } from 'zod'
import { getSql, buildSetClause } from '../db'
import { clearTradingConfigCache } from '../trading-config'
import type { TradingConfig, SectorAllocation } from '../../types'

const tradingConfigUpdateSchema = z.object({
  min_cash_reserve: z.number().int().min(0).optional(),
  max_risk_per_trade: z.number().int().min(0).optional(),
  low_cash_threshold: z.number().int().min(0).optional(),
  max_concurrent_positions: z.number().int().min(1).max(10).optional(),
  transaction_cost_pct: z.number().min(0).max(1).optional(),
  monthly_contribution: z.number().int().min(0).optional(),
  concentration_exit_pct: z.number().min(0).max(100).optional(),
  swing_trim_weight_pct: z.number().min(0).max(100).optional(),
  swing_trim_gain_pct: z.number().min(0).max(100).optional(),
  longterm_trim_weight_high_pct: z.number().min(0).max(100).optional(),
  longterm_trim_weight_med_pct: z.number().min(0).max(100).optional(),
  longterm_review_weight_pct: z.number().min(0).max(100).optional(),
  sector_concentration_high_pct: z.number().min(0).max(100).optional(),
  sector_concentration_med_pct: z.number().min(0).max(100).optional(),
  breakeven_gain_pct: z.number().min(0).max(100).optional(),
  half_trail_gain_pct: z.number().min(0).max(100).optional(),
  tight_trail_gain_pct: z.number().min(0).max(100).optional(),
  tight_current_floor_pct: z.number().min(0).max(100).optional(),
  tight_gain_lock_pct: z.number().min(0).max(100).optional(),
  longterm_catastrophic_pct: z.number().min(0).max(100).optional(),
  full_winrate_threshold: z.number().min(0).max(100).optional(),
  reduced_winrate_threshold: z.number().min(0).max(100).optional(),
  half_winrate_threshold: z.number().min(0).max(100).optional(),
  minimal_scale_factor: z.number().min(0).max(1).optional(),
  retro_severe_winrate: z.number().min(0).max(100).optional(),
  retro_moderate_winrate: z.number().min(0).max(100).optional(),
  retro_severe_max_entries: z.number().int().min(0).max(10).optional(),
  retro_severe_min_rr: z.number().min(0).max(20).optional(),
  retro_severe_scale: z.number().min(0).max(1).optional(),
  retro_moderate_max_entries: z.number().int().min(0).max(10).optional(),
  retro_moderate_min_rr: z.number().min(0).max(20).optional(),
})

export const getTradingConfig = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`SELECT * FROM trading_config LIMIT 1`
  if (!rows[0]) {
    throw new Error('Config not found')
  }
  return rows[0] as TradingConfig
})

export const updateTradingConfig = createServerFn({ method: 'POST' })
  .inputValidator((data: z.infer<typeof tradingConfigUpdateSchema>) => {
    const parsed = tradingConfigUpdateSchema.parse(data)
    return parsed
  })
  .handler(async ({ data }) => {
    const updates: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(data)) {
      if (value !== undefined) updates[key] = value
    }

    if (Object.keys(updates).length === 0) {
      throw new Error('No fields to update')
    }

    const sql = getSql()
    const { clause, values } = buildSetClause(updates, 1)
    const rows = await sql(
      `UPDATE trading_config SET ${clause}, updated_at = NOW() WHERE id = 1 RETURNING *`,
      values,
    )

    clearTradingConfigCache()

    return rows[0] as TradingConfig
  })

const sectorAllocationUpsertSchema = z.object({
  sector_name: z
    .string()
    .min(1)
    .max(50)
    .regex(/^[a-z_]+$/, 'Must be lowercase snake_case (e.g. real_estate)'),
  target_pct: z.number().min(0).max(100),
})

export const getSectorAllocations = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT id, sector_name, target_pct, updated_at
    FROM sector_allocations
    ORDER BY target_pct DESC
  `
  return rows as SectorAllocation[]
})

export const upsertSectorAllocation = createServerFn({ method: 'POST' })
  .inputValidator((data: z.infer<typeof sectorAllocationUpsertSchema>) => {
    return sectorAllocationUpsertSchema.parse(data)
  })
  .handler(async ({ data }) => {
    const { sector_name, target_pct } = data
    const sql = getSql()
    const rows = await sql`
      INSERT INTO sector_allocations (sector_name, target_pct, updated_at)
      VALUES (${sector_name}, ${target_pct}, NOW())
      ON CONFLICT (sector_name) DO UPDATE
        SET target_pct = ${target_pct}, updated_at = NOW()
      RETURNING *
    `
    return rows[0] as SectorAllocation
  })

export const deleteSectorAllocation = createServerFn({ method: 'POST' })
  .inputValidator((data: { sector_name: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    await sql`DELETE FROM sector_allocations WHERE sector_name = ${data.sector_name}`
    return { ok: true }
  })
