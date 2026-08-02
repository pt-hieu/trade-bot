/**
 * Alert-to-trade matching — links trades to their source alerts at creation time.
 *
 * When a user creates or closes a trade, find the best matching alert and:
 * 1. Set source_alert_id on the trade
 * 2. Insert into alert_effectiveness with was_converted=true
 * 3. Mark the alert as triggered
 */

import { getSql } from '../db'

interface TradeForMatching {
  id: string
  ticker: string
  entryPriceVnd: number
  entryDate: string
  status: string
  plPct?: number | null
}

/**
 * Link a newly created/closed trade to its best matching alert.
 * BUY trades match BUY/LIMIT_BUY/ADD alerts.
 * CLOSED trades match TRIM/EXIT/STOP alerts.
 * Non-fatal — trade creation never fails because of alert matching.
 */
export async function linkTradeToAlert(trade: TradeForMatching): Promise<number | null> {
  const sql = getSql()

  try {
    // Find best matching alert: same ticker, compatible action, within +/-2 days
    const alerts =
      trade.status === 'OPEN'
        ? await sql`
            SELECT id, recommended_action, source
            FROM alerts
            WHERE ticker = ${trade.ticker}
              AND recommended_action IN ('BUY', 'LIMIT_BUY', 'ADD')
              AND status IN ('active', 'triggered')
              AND source_date BETWEEN ${trade.entryDate}::date - 2 AND ${trade.entryDate}::date + 2
            ORDER BY
              ABS(COALESCE(entry_price, 0) - ${trade.entryPriceVnd}) ASC,
              created_at DESC
            LIMIT 1
          `
        : await sql`
            SELECT id, recommended_action, source
            FROM alerts
            WHERE ticker = ${trade.ticker}
              AND recommended_action IN ('TRIM', 'EXIT', 'STOP')
              AND status IN ('active', 'triggered')
              AND source_date BETWEEN ${trade.entryDate}::date - 2 AND ${trade.entryDate}::date + 2
            ORDER BY created_at DESC
            LIMIT 1
          `

    if (alerts.length === 0) return null

    const alert = alerts[0]
    const alertId = Number(alert.id)
    const actualAction = trade.status === 'OPEN' ? 'BUY' : 'SELL'

    // Link trade -> alert
    await sql`
      UPDATE trades_calculated SET source_alert_id = ${alertId}
      WHERE id = ${trade.id}
    `

    // Record in alert_effectiveness (upsert — retro pipeline may also insert)
    await sql`
      INSERT INTO alert_effectiveness (
        alert_id, trade_id, ticker, alert_source,
        recommended_action, actual_action, was_converted, pnl_pct, scan_date
      ) VALUES (
        ${alertId}, ${trade.id}::uuid, ${trade.ticker},
        ${alert.source}, ${alert.recommended_action},
        ${actualAction}, TRUE, ${trade.plPct ?? null},
        ${trade.entryDate}::date
      )
      ON CONFLICT (alert_id, trade_id) WHERE trade_id IS NOT NULL
      DO UPDATE SET pnl_pct = COALESCE(EXCLUDED.pnl_pct, alert_effectiveness.pnl_pct),
                    actual_action = EXCLUDED.actual_action
    `

    // Mark alert as triggered
    await sql`
      UPDATE alerts
      SET status = 'triggered', triggered_at = NOW(), updated_at = NOW()
      WHERE id = ${alertId} AND status = 'active'
    `

    return alertId
  } catch (error) {
    console.error('Alert matching failed (non-fatal):', error)
    return null
  }
}

/**
 * Update alert_effectiveness P/L when a trade is closed.
 * Finds the existing effectiveness row by trade_id and fills in pnl_pct.
 */
export async function updateAlertPnlOnClose(tradeId: string, plPct: number): Promise<void> {
  const sql = getSql()
  try {
    await sql`
      UPDATE alert_effectiveness
      SET pnl_pct = ${plPct}
      WHERE trade_id = ${tradeId}::uuid AND pnl_pct IS NULL
    `
  } catch (error) {
    console.error('Alert P/L update failed (non-fatal):', error)
  }
}
