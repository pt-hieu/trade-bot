/**
 * Pipeline Reporter tools — surfaces pre-computed data from morning brief, midday check, and retro.
 * These tools REPORT facts from automated pipelines; they do NOT perform analysis.
 */
import { z } from 'zod'
import type { Tool } from 'ai'
import { getSql } from './shared'
import { formatAfternoonPlanProse } from '../../../server/fns/midday-prose'

/** Get today's date in Vietnam timezone (UTC+7) as YYYY-MM-DD */
function vnToday(): string {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Ho_Chi_Minh' })
}

// ─── Morning Recommendations ──────────────────────────────────────────────────

const _morningRecsSchema = z.object({
  date: z
    .string()
    .optional()
    .describe('Date in YYYY-MM-DD format (default: today in Vietnam timezone)'),
  ticker: z.string().optional().describe('Filter to a specific ticker, e.g. "FPT"'),
})

const get_morning_recommendations: Tool = {
  description:
    "Get morning brief recommendations for a date — tickers, actions (BUY/SELL/HOLD/WATCH/EXIT/etc), entry/stop/target prices, position sizing, strategy, and confidence. Grouped by section: MY_HOLDINGS (existing positions), TOP_PICKS (new entries), and others.",
  inputSchema: _morningRecsSchema,
  execute: async (input: z.infer<typeof _morningRecsSchema>) => {
    const sql = getSql()
    const date = input.date ?? vnToday()
    const rows = input.ticker
      ? await sql`
          SELECT dr.record_date, dr.trading_mode,
                 rec.ticker, rec.action, rec.entry_price_vnd, rec.stop_price_vnd,
                 rec.target_price_vnd, rec.size_shares, rec.rationale, rec.section,
                 rec.strategy, rec.strategy_confidence
          FROM daily_records dr
          JOIN daily_recommendations rec ON rec.record_id = dr.id
          WHERE dr.record_date = ${date}::date
            AND rec.ticker = ${input.ticker.toUpperCase()}
          ORDER BY rec.section, rec.ticker
        `
      : await sql`
          SELECT dr.record_date, dr.trading_mode,
                 rec.ticker, rec.action, rec.entry_price_vnd, rec.stop_price_vnd,
                 rec.target_price_vnd, rec.size_shares, rec.rationale, rec.section,
                 rec.strategy, rec.strategy_confidence
          FROM daily_records dr
          JOIN daily_recommendations rec ON rec.record_id = dr.id
          WHERE dr.record_date = ${date}::date
          ORDER BY rec.section, rec.ticker
        `

    if (!rows.length) {
      return JSON.stringify({ date, error: `No morning brief recommendations found for ${date}` })
    }

    return JSON.stringify({
      date: rows[0].record_date,
      trading_mode: rows[0].trading_mode,
      count: rows.length,
      recommendations: rows.map((r) => ({
        ticker: r.ticker,
        action: r.action,
        section: r.section,
        entry_price: r.entry_price_vnd != null ? Number(r.entry_price_vnd) / 1000 : null,
        stop_price: r.stop_price_vnd != null ? Number(r.stop_price_vnd) / 1000 : null,
        target_price: r.target_price_vnd != null ? Number(r.target_price_vnd) / 1000 : null,
        size_shares: r.size_shares,
        strategy: r.strategy,
        strategy_confidence: r.strategy_confidence != null ? Number(r.strategy_confidence) : null,
        rationale: r.rationale,
      })),
    })
  },
}

// ─── Morning Position Alerts ──────────────────────────────────────────────────

const _positionAlertsSchema = z.object({
  date: z
    .string()
    .optional()
    .describe('Date in YYYY-MM-DD format (default: today in Vietnam timezone)'),
  ticker: z.string().optional().describe('Filter to a specific ticker'),
})

const get_position_alerts: Tool = {
  description:
    'Get morning position alerts — the multi-analyst ensemble consensus for existing holdings. Shows urgency (high/medium/low), recommended action, consensus strength, dissenting views, and proximity to entry/stop/target.',
  inputSchema: _positionAlertsSchema,
  execute: async (input: z.infer<typeof _positionAlertsSchema>) => {
    const sql = getSql()
    const date = input.date ?? vnToday()
    const rows = input.ticker
      ? await sql`
          SELECT ticker, action, urgency, reason,
                 target_price, stop_price, consensus,
                 dissenting_views, entry_price, pct_from_entry,
                 weight_pct, volume_signal
          FROM morning_position_alerts
          WHERE scan_date = ${date}::date
            AND ticker = ${input.ticker.toUpperCase()}
          ORDER BY
            CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            ticker
        `
      : await sql`
          SELECT ticker, action, urgency, reason,
                 target_price, stop_price, consensus,
                 dissenting_views, entry_price, pct_from_entry,
                 weight_pct, volume_signal
          FROM morning_position_alerts
          WHERE scan_date = ${date}::date
          ORDER BY
            CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            ticker
        `

    if (!rows.length) {
      return JSON.stringify({ date, error: `No position alerts found for ${date}` })
    }

    return JSON.stringify({
      date,
      count: rows.length,
      alerts: rows.map((r) => ({
        ticker: r.ticker,
        action: r.action,
        urgency: r.urgency,
        consensus: r.consensus,
        dissenting_views: r.dissenting_views,
        reason: r.reason,
        entry_price: r.entry_price != null ? Number(r.entry_price) / 1000 : null,
        stop_price: r.stop_price != null ? Number(r.stop_price) / 1000 : null,
        target_price: r.target_price != null ? Number(r.target_price) / 1000 : null,
        pct_from_entry: r.pct_from_entry != null ? Number(r.pct_from_entry) : null,
        weight_pct: r.weight_pct != null ? Number(r.weight_pct) : null,
        volume_signal: r.volume_signal,
      })),
    })
  },
}

// ─── Midday Snapshot ──────────────────────────────────────────────────────────

const _middaySchema = z.object({
  date: z
    .string()
    .optional()
    .describe('Date in YYYY-MM-DD format (default: today in Vietnam timezone)'),
})

const get_midday_snapshot: Tool = {
  description:
    'Get midday check snapshot — trading mode, entries hit (morning recs that price reached), big movers (>= 3% intraday), and position alerts near stops or targets (within 2%). Runs at ~12:00 PM Vietnam time.',
  inputSchema: _middaySchema,
  execute: async (input: z.infer<typeof _middaySchema>) => {
    const sql = getSql()
    const date = input.date ?? vnToday()

    const [checkRows] = await sql`
      SELECT id, trading_mode, morning_reflection, afternoon_plan,
             capital_note, recommendation_overrides
      FROM midday_checks
      WHERE scan_date = ${date}::date
    `

    if (!checkRows) {
      return JSON.stringify({ date, error: `No midday check data found for ${date}` })
    }

    const [entriesHit, bigMovers, positionAlerts] = await Promise.all([
      sql`
        SELECT ticker, recommended_entry_vnd, actual_low_vnd, current_price_vnd, status
        FROM midday_entries_hit
        WHERE midday_id = ${checkRows.id}
        ORDER BY ticker
      `,
      sql`
        SELECT ticker, open_price_vnd, current_price_vnd, change_pct, direction
        FROM midday_big_movers
        WHERE midday_id = ${checkRows.id}
        ORDER BY ABS(change_pct) DESC
      `,
      sql`
        SELECT ticker, current_price_vnd, level_vnd, level_type, distance_pct, urgency
        FROM midday_position_alerts
        WHERE midday_id = ${checkRows.id}
        ORDER BY
          CASE urgency WHEN 'high' THEN 1 ELSE 2 END,
          ABS(distance_pct)
      `,
    ])

    const afternoonPlanRaw = Array.isArray(checkRows.afternoon_plan) ? checkRows.afternoon_plan : []
    const afternoonPlanProse = formatAfternoonPlanProse(afternoonPlanRaw, null)

    return JSON.stringify({
      date,
      trading_mode: checkRows.trading_mode,
      morning_reflection: checkRows.morning_reflection,
      afternoon_plan: afternoonPlanProse,
      afternoon_plan_raw: afternoonPlanRaw,
      capital_note: checkRows.capital_note,
      recommendation_overrides: checkRows.recommendation_overrides,
      entries_hit: entriesHit.map((e) => ({
        ticker: e.ticker,
        recommended_entry: e.recommended_entry_vnd != null ? Number(e.recommended_entry_vnd) / 1000 : null,
        actual_low: e.actual_low_vnd != null ? Number(e.actual_low_vnd) / 1000 : null,
        current_price: e.current_price_vnd != null ? Number(e.current_price_vnd) / 1000 : null,
        status: e.status,
      })),
      big_movers: bigMovers.map((m) => ({
        ticker: m.ticker,
        open_price: m.open_price_vnd != null ? Number(m.open_price_vnd) / 1000 : null,
        current_price: m.current_price_vnd != null ? Number(m.current_price_vnd) / 1000 : null,
        change_pct: m.change_pct != null ? Number(m.change_pct) : null,
        direction: m.direction,
      })),
      position_alerts: positionAlerts.map((a) => ({
        ticker: a.ticker,
        current_price: a.current_price_vnd != null ? Number(a.current_price_vnd) / 1000 : null,
        level: a.level_vnd != null ? Number(a.level_vnd) / 1000 : null,
        level_type: a.level_type,
        distance_pct: a.distance_pct != null ? Number(a.distance_pct) : null,
        urgency: a.urgency,
      })),
    })
  },
}

// ─── Daily Evaluations ────────────────────────────────────────────────────────

const _evaluationsSchema = z.object({
  date: z
    .string()
    .optional()
    .describe('Date in YYYY-MM-DD format (default: today in Vietnam timezone)'),
  ticker: z.string().optional().describe('Filter to a specific ticker'),
  status: z
    .enum(['WIN', 'LOSS', 'PENDING', 'MISSED', 'EXCLUDED'])
    .optional()
    .describe('Filter by evaluation status'),
})

const get_daily_evaluations: Tool = {
  description:
    'Get retro evaluation results for a date — how each recommendation actually performed. Shows entry/stop/target hit booleans, EOD price, P/L percentage, win/loss status, and error analysis. Available after 3:30 PM Vietnam time.',
  inputSchema: _evaluationsSchema,
  execute: async (input: z.infer<typeof _evaluationsSchema>) => {
    const sql = getSql()
    const date = input.date ?? vnToday()

    const rows =
      input.ticker && input.status
        ? await sql`
            SELECT de.ticker, de.recommendation, de.section,
                   de.entry_hit, de.stop_hit, de.target_hit,
                   de.eod_price_vnd, de.pnl_percent, de.status, de.won, de.analysis
            FROM daily_records dr
            JOIN daily_evaluations de ON de.record_id = dr.id
            WHERE dr.record_date = ${date}::date
              AND de.ticker = ${input.ticker.toUpperCase()}
              AND de.status = ${input.status}
            ORDER BY de.status, de.ticker
          `
        : input.ticker
          ? await sql`
              SELECT de.ticker, de.recommendation, de.section,
                     de.entry_hit, de.stop_hit, de.target_hit,
                     de.eod_price_vnd, de.pnl_percent, de.status, de.won, de.analysis
              FROM daily_records dr
              JOIN daily_evaluations de ON de.record_id = dr.id
              WHERE dr.record_date = ${date}::date
                AND de.ticker = ${input.ticker.toUpperCase()}
              ORDER BY de.status, de.ticker
            `
          : input.status
            ? await sql`
                SELECT de.ticker, de.recommendation, de.section,
                       de.entry_hit, de.stop_hit, de.target_hit,
                       de.eod_price_vnd, de.pnl_percent, de.status, de.won, de.analysis
                FROM daily_records dr
                JOIN daily_evaluations de ON de.record_id = dr.id
                WHERE dr.record_date = ${date}::date
                  AND de.status = ${input.status}
                ORDER BY de.status, de.ticker
              `
            : await sql`
                SELECT de.ticker, de.recommendation, de.section,
                       de.entry_hit, de.stop_hit, de.target_hit,
                       de.eod_price_vnd, de.pnl_percent, de.status, de.won, de.analysis
                FROM daily_records dr
                JOIN daily_evaluations de ON de.record_id = dr.id
                WHERE dr.record_date = ${date}::date
                ORDER BY de.status, de.ticker
              `

    if (!rows.length) {
      return JSON.stringify({ date, error: `No evaluations found for ${date} — retro may not have run yet (runs at 3:30 PM VN)` })
    }

    // Tally by status
    const tally: Record<string, number> = {}
    for (const r of rows) {
      tally[r.status as string] = (tally[r.status as string] ?? 0) + 1
    }

    return JSON.stringify({
      date,
      count: rows.length,
      summary: tally,
      evaluations: rows.map((r) => ({
        ticker: r.ticker,
        recommendation: r.recommendation,
        section: r.section,
        entry_hit: r.entry_hit,
        stop_hit: r.stop_hit,
        target_hit: r.target_hit,
        eod_price: r.eod_price_vnd != null ? Number(r.eod_price_vnd) / 1000 : null,
        pnl_percent: r.pnl_percent != null ? Number(r.pnl_percent) : null,
        status: r.status,
        won: r.won,
        analysis: r.analysis,
      })),
    })
  },
}

// ─── Daily Record ─────────────────────────────────────────────────────────────

const _dailyRecordSchema = z.object({
  date: z
    .string()
    .optional()
    .describe('Specific date (YYYY-MM-DD, default: today in Vietnam timezone)'),
  days: z
    .number()
    .min(1)
    .max(30)
    .optional()
    .describe('Number of recent days to return (default: 1, max: 30)'),
})

const get_daily_record: Tool = {
  description:
    'Get the daily record summary — pre-computed hit rates, win rates, best/worst calls, and key insight for a date or recent date range. This is the retro pipeline executive summary.',
  inputSchema: _dailyRecordSchema,
  execute: async (input: z.infer<typeof _dailyRecordSchema>) => {
    const sql = getSql()
    const date = input.date ?? vnToday()
    const days = input.days ?? 1

    const rows = await sql`
      SELECT record_date, market_regime, trading_mode,
             total_recs, entry_hit_rate, win_rate,
             best_call, worst_call, key_insight,
             mode_compliance
      FROM daily_records
      WHERE record_date <= ${date}::date
        AND total_recs IS NOT NULL
      ORDER BY record_date DESC
      LIMIT ${days}
    `

    if (!rows.length) {
      return JSON.stringify({ date, error: `No daily record found for ${date} — retro may not have run yet` })
    }

    const records = rows.map((r) => ({
      date: r.record_date,
      market_regime: r.market_regime,
      trading_mode: r.trading_mode,
      total_recs: r.total_recs,
      entry_hit_rate: r.entry_hit_rate != null ? Number(r.entry_hit_rate) : null,
      win_rate: r.win_rate != null ? Number(r.win_rate) : null,
      best_call: r.best_call,
      worst_call: r.worst_call,
      key_insight: r.key_insight,
      mode_compliance: r.mode_compliance,
    }))

    return JSON.stringify(days === 1 ? records[0] : records)
  },
}

// ─── Calibration Insights ─────────────────────────────────────────────────────

const _calibrationSchema = z.object({
  days: z
    .number()
    .min(1)
    .max(30)
    .optional()
    .describe('Number of recent days to return (default: 7, max: 30)'),
})

const get_calibration_insights: Tool = {
  description:
    'Get entry/stop/target calibration stats from the retro pipeline — how accurate are morning brief price levels? Shows entry gap (reachability), stop adequacy vs ATR, and predicted vs actual R:R. Flag: pct_entries_unreachable > 30% or pct_stops_too_tight > 40% = calibration problem.',
  inputSchema: _calibrationSchema,
  execute: async (input: z.infer<typeof _calibrationSchema>) => {
    const sql = getSql()
    const days = input.days ?? 7

    const rows = await sql`
      SELECT scan_date,
             avg_entry_gap_pct, pct_entries_unreachable,
             avg_stop_vs_atr, pct_stops_too_tight,
             avg_predicted_rr, avg_actual_rr,
             target_hit_rate, sample_size
      FROM calibration_insights
      ORDER BY scan_date DESC
      LIMIT ${days}
    `

    if (!rows.length) {
      return JSON.stringify({ error: 'No calibration data found' })
    }

    return JSON.stringify({
      days_returned: rows.length,
      insights: rows.map((r) => ({
        date: r.scan_date,
        avg_entry_gap_pct: r.avg_entry_gap_pct != null ? Number(r.avg_entry_gap_pct) : null,
        pct_entries_unreachable: r.pct_entries_unreachable != null ? Number(r.pct_entries_unreachable) : null,
        avg_stop_vs_atr: r.avg_stop_vs_atr != null ? Number(r.avg_stop_vs_atr) : null,
        pct_stops_too_tight: r.pct_stops_too_tight != null ? Number(r.pct_stops_too_tight) : null,
        avg_predicted_rr: r.avg_predicted_rr != null ? Number(r.avg_predicted_rr) : null,
        avg_actual_rr: r.avg_actual_rr != null ? Number(r.avg_actual_rr) : null,
        target_hit_rate: r.target_hit_rate != null ? Number(r.target_hit_rate) : null,
        sample_size: r.sample_size,
      })),
    })
  },
}

// ─── Strategy Directive ───────────────────────────────────────────────────────

const _directiveSchema = z.object({
  date: z
    .string()
    .optional()
    .describe('Date in YYYY-MM-DD format (default: today in Vietnam timezone)'),
})

const get_strategy_directive: Tool = {
  description:
    "Get the daily strategic directive — today's theme, stance (AGGRESSIVE/NEUTRAL/DEFENSIVE/CASH_PRESERVATION), sector focus, and hard trading constraints (budget, max new entries, min R:R, urgency tier). Set by the morning brief pipeline.",
  inputSchema: _directiveSchema,
  execute: async (input: z.infer<typeof _directiveSchema>) => {
    const sql = getSql()
    const date = input.date ?? vnToday()

    const [row] = await sql`
      SELECT scan_date, directive, constraints
      FROM strategy_directives
      WHERE scan_date = ${date}::date
    `

    if (!row) {
      return JSON.stringify({ date, error: `No strategy directive found for ${date}` })
    }

    return JSON.stringify({
      date: row.scan_date,
      directive: row.directive,
      constraints: row.constraints,
    })
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const pipelineTools = {
  get_morning_recommendations,
  get_position_alerts,
  get_midday_snapshot,
  get_daily_evaluations,
  get_daily_record,
  get_calibration_insights,
  get_strategy_directive,
}
