import { createServerFn } from '@tanstack/react-start'
import { getSql, buildSetClause } from '../db'
import { syncGoalProgress } from '../goal-sync'
import { getTransactionCostPct } from '../trading-config'
import { linkTradeToAlert, updateAlertPnlOnClose } from './alert-matching'

// ─── Types ────────────────────────────────────────────────────────────────────

interface TradeInput {
  ticker: string
  entry_date: string
  entry_price_vnd: number
  shares: number
  strategy: 'Bounce' | 'Trend' | 'Breakout' | 'Divergence' | 'Mean Reversion' | 'Momentum' | 'Pullback' | null
  plan_type: 'SWING' | 'LONGTERM'
  status: 'OPEN' | 'CLOSED'
  exit_date?: string | null
  exit_price_vnd?: number | null
  exit_shares?: number
}

interface TradesGetParams {
  all?: boolean
}

interface TradeUpdateParams {
  id: string
  input: Partial<TradeInput>
}

interface TradeDeleteParams {
  id: string
}

// ─── GET /trades ───────────────────────────────────────────────────────────────

export const getTrades = createServerFn({ method: 'GET' })
  .inputValidator((data: TradesGetParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const showAll = data.all === true

    const rows = showAll
      ? await sql`
          SELECT
            id, ticker, plan_type, strategy, entry_date, entry_price_vnd,
            exit_date, exit_price_vnd, shares, buy_total_vnd, pl_gross_vnd,
            pl_net_vnd,
            ROUND(pl_pct::numeric, 2) AS pl_pct,
            exit_date - entry_date AS days_held,
            CASE WHEN status != 'CLOSED' THEN NULL WHEN pl_net_vnd >= 0 THEN 'WIN' ELSE 'LOSS' END AS result,
            status
          FROM trades_calculated
          ORDER BY COALESCE(exit_date, entry_date) DESC
        `
      : await sql`
          SELECT
            id, ticker, plan_type, strategy, entry_date, entry_price_vnd,
            exit_date, exit_price_vnd, shares, buy_total_vnd, pl_gross_vnd,
            pl_net_vnd, pl_pct, days_held, result, status
          FROM v_recent_trades
          ORDER BY entry_date DESC
          LIMIT 5
        `

    return rows
  })

// ─── POST /trades ──────────────────────────────────────────────────────────────

export const createTrade = createServerFn({ method: 'POST' })
  .inputValidator((data: TradeInput) => data)
  .handler(async ({ data: input }) => {
    const sql = getSql()
    const buy_total_vnd = input.entry_price_vnd * input.shares

    let sell_total_vnd = 0
    let pl_gross_vnd = 0
    let transaction_cost_vnd = 0
    let pl_net_vnd = 0
    let pl_pct = 0

    if (input.status === 'CLOSED' && input.exit_price_vnd) {
      const txCostPct = await getTransactionCostPct()
      sell_total_vnd = input.exit_price_vnd * input.shares
      pl_gross_vnd = sell_total_vnd - buy_total_vnd
      transaction_cost_vnd = Math.round((buy_total_vnd + sell_total_vnd) * txCostPct)
      pl_net_vnd = pl_gross_vnd - transaction_cost_vnd
      pl_pct = buy_total_vnd > 0 ? Number(((pl_net_vnd / buy_total_vnd) * 100).toFixed(4)) : 0
    }

    const rows = await sql`
      INSERT INTO trades_calculated (
        ticker,
        entry_date,
        entry_price_vnd,
        shares,
        strategy,
        plan_type,
        status,
        buy_total_vnd,
        exit_date,
        exit_price_vnd,
        sell_total_vnd,
        pl_gross_vnd,
        transaction_cost_vnd,
        pl_net_vnd,
        pl_pct
      ) VALUES (
        ${input.ticker.toUpperCase()},
        ${input.entry_date},
        ${input.entry_price_vnd},
        ${input.shares},
        ${input.strategy},
        ${input.plan_type},
        ${input.status},
        ${buy_total_vnd},
        ${input.exit_date ?? null},
        ${input.exit_price_vnd ?? null},
        ${sell_total_vnd},
        ${pl_gross_vnd},
        ${transaction_cost_vnd},
        ${pl_net_vnd},
        ${pl_pct}
      )
      RETURNING *
    `

    await syncGoalProgress()

    // Link to matching alert (fire-and-forget, non-fatal)
    const created = rows[0]
    linkTradeToAlert({
      id: created.id as string,
      ticker: input.ticker.toUpperCase(),
      entryPriceVnd: input.entry_price_vnd,
      entryDate: input.entry_date,
      status: input.status,
      plPct: input.status === 'CLOSED' ? pl_pct : null,
    }).catch((error) => console.error('[alert-matching]', error))

    return created
  })

// ─── PUT /trades/:id ───────────��─────────────────────────────────────��─────────

export const updateTrade = createServerFn({ method: 'POST' })
  .inputValidator((data: TradeUpdateParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { id, input } = data

    const existing = await sql`
      SELECT ticker, entry_date, entry_price_vnd, shares, strategy, plan_type, buy_total_vnd, status
      FROM trades_calculated WHERE id = ${id}
    `
    if (existing.length === 0) {
      throw new Error('Trade not found')
    }
    const trade = existing[0]

    // Partial close: split into CLOSED + remaining OPEN
    if (
      input.status === 'CLOSED' &&
      input.exit_price_vnd &&
      input.exit_shares &&
      input.exit_shares < (trade.shares as number)
    ) {
      const exitShares = input.exit_shares
      const remaining = (trade.shares as number) - exitShares
      const txCostPct = await getTransactionCostPct()
      const exitBuyTotal = (trade.entry_price_vnd as number) * exitShares
      const sellTotal = input.exit_price_vnd * exitShares
      const plGross = sellTotal - exitBuyTotal
      const txCost = Math.round((exitBuyTotal + sellTotal) * txCostPct)
      const plNet = plGross - txCost
      const plPct = exitBuyTotal > 0 ? Number(((plNet / exitBuyTotal) * 100).toFixed(4)) : 0

      const closedRows = await sql`
        INSERT INTO trades_calculated (
          ticker, entry_date, entry_price_vnd, shares, strategy, plan_type,
          status, exit_date, exit_price_vnd, buy_total_vnd,
          sell_total_vnd, pl_gross_vnd, transaction_cost_vnd, pl_net_vnd, pl_pct
        ) VALUES (
          ${trade.ticker}, ${trade.entry_date}, ${trade.entry_price_vnd}, ${exitShares},
          ${input.strategy ?? trade.strategy}, ${trade.plan_type},
          'CLOSED', ${input.exit_date}, ${input.exit_price_vnd}, ${exitBuyTotal},
          ${sellTotal}, ${plGross}, ${txCost}, ${plNet}, ${plPct}
        )
        RETURNING id
      `

      // Link closed portion to TRIM/EXIT alert
      if (closedRows.length > 0) {
        linkTradeToAlert({
          id: closedRows[0].id as string,
          ticker: trade.ticker as string,
          entryPriceVnd: trade.entry_price_vnd as number,
          entryDate: (input.exit_date ?? trade.entry_date) as string,
          status: 'CLOSED',
          plPct,
        }).catch((error) => console.error('[alert-matching]', error))
      }

      // Update P/L on original trade's alert link
      updateAlertPnlOnClose(id, plPct).catch((error) => console.error('[alert-matching]', error))

      const remainingBuyTotal = (trade.entry_price_vnd as number) * remaining
      await sql`
        UPDATE trades_calculated
        SET shares = ${remaining}, buy_total_vnd = ${remainingBuyTotal}
        WHERE id = ${id}
      `

      await sql`
        UPDATE portfolio_holdings
        SET shares = shares - ${exitShares}, updated_at = NOW()
        WHERE ticker = ${trade.ticker}
      `
      await sql`
        DELETE FROM portfolio_holdings
        WHERE ticker = ${trade.ticker} AND shares <= 0
      `

      // Increase cash by sell proceeds
      await sql`
        UPDATE portfolio_holdings
        SET avg_cost_vnd = avg_cost_vnd + ${sellTotal}, updated_at = NOW()
        WHERE ticker = 'CASH' AND holding_type = 'Cash'
      `

      await syncGoalProgress()

      const updated = await sql`SELECT * FROM trades_calculated WHERE id = ${id}`
      return updated[0]
    }

    // Full close or field updates
    const updates: Record<string, unknown> = {}

    if (input.ticker !== undefined) updates.ticker = input.ticker.toUpperCase()
    if (input.entry_date !== undefined) updates.entry_date = input.entry_date
    if (input.entry_price_vnd !== undefined) updates.entry_price_vnd = input.entry_price_vnd
    if (input.shares !== undefined) updates.shares = input.shares
    if (input.strategy !== undefined) updates.strategy = input.strategy
    if (input.plan_type !== undefined) updates.plan_type = input.plan_type
    if (input.status !== undefined) updates.status = input.status
    if (input.exit_date !== undefined) updates.exit_date = input.exit_date
    if (input.exit_price_vnd !== undefined) updates.exit_price_vnd = input.exit_price_vnd

    if (input.entry_price_vnd !== undefined && input.shares !== undefined) {
      updates.buy_total_vnd = input.entry_price_vnd * input.shares
    }

    if (input.status === 'CLOSED' && input.exit_price_vnd) {
      const txCostPct = await getTransactionCostPct()
      const shares = input.shares ?? (trade.shares as number)
      const buyTotal = (updates.buy_total_vnd as number) ?? (trade.buy_total_vnd as number)
      const sellTotal = input.exit_price_vnd * shares
      const plGross = sellTotal - buyTotal
      const txCost = Math.round((buyTotal + sellTotal) * txCostPct)
      const plNet = plGross - txCost

      updates.sell_total_vnd = sellTotal
      updates.pl_gross_vnd = plGross
      updates.transaction_cost_vnd = txCost
      updates.pl_net_vnd = plNet
      updates.pl_pct = buyTotal > 0 ? Number(((plNet / buyTotal) * 100).toFixed(4)) : 0
    }

    if (Object.keys(updates).length === 0) {
      throw new Error('No fields to update')
    }

    const { clause, values } = buildSetClause(updates)
    const rows = await sql(
      `UPDATE trades_calculated SET ${clause} WHERE id = $1 RETURNING *`,
      [id, ...values]
    )

    if (rows.length === 0) {
      throw new Error('Trade not found')
    }

    await syncGoalProgress()

    // Alert matching on close
    if (input.status === 'CLOSED' && input.exit_price_vnd) {
      const closedTicker = (input.ticker?.toUpperCase() ?? trade.ticker) as string
      const exitDate = (input.exit_date ?? input.entry_date ?? trade.entry_date) as string
      linkTradeToAlert({
        id,
        ticker: closedTicker,
        entryPriceVnd: (input.entry_price_vnd ?? trade.entry_price_vnd) as number,
        entryDate: exitDate,
        status: 'CLOSED',
        plPct: (updates.pl_pct as number) ?? null,
      }).catch((error) => console.error('[alert-matching]', error))
    }
    // Update P/L on existing alert link (covers re-edits of closed trades)
    if (updates.pl_pct !== undefined) {
      updateAlertPnlOnClose(id, updates.pl_pct as number).catch((error) => console.error('[alert-matching]', error))
    }

    return rows[0]
  })

// ─── DELETE /trades/:id ─��──────────────────────────────────────────────────────

export const deleteTrade = createServerFn({ method: 'POST' })
  .inputValidator((data: TradeDeleteParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { id } = data

    const rows = await sql`
      DELETE FROM trades_calculated
      WHERE id = ${id}
      RETURNING id
    `

    if (rows.length === 0) {
      throw new Error('Trade not found')
    }

    await syncGoalProgress()

    return { success: true }
  })
