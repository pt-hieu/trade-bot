import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { getLatestPrices } from '../vnstock'
import { toDateStr } from '../../lib/date'
import { stripAuditTags } from '../../lib/audit-tags'
import { formatAfternoonPlanProse } from './midday-prose'

export const getScanDates = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT scan_date FROM daily_scans
    ORDER BY scan_date DESC
    LIMIT 60
  `
  return rows.map((r) => toDateStr(r.scan_date))
})

export const getDailyIntel = createServerFn({ method: 'GET' })
  .inputValidator((data: { date?: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()

    const rawDate = data.date ?? (
      await sql`SELECT scan_date FROM daily_scans ORDER BY scan_date DESC LIMIT 1`
    )[0]?.scan_date
    const scanDate = rawDate ? toDateStr(rawDate) : null

    if (!scanDate) {
      throw new Error('No scan data available')
    }

    const [regimeRows, macroRows, flowRows, rotationRows, articleRows, vnidxPrices] =
      await Promise.all([
        sql`
          SELECT mr.regime, mr.regime_confidence, mr.key_signal, mr.recommendation
          FROM market_regimes mr
          WHERE mr.scan_date = ${scanDate}
        `,
        sql`
          SELECT dxy_value, dxy_change_pct, dxy_signal_value, vix_value, vix_change_pct,
                 vix_signal_value, usd_vnd_rate, usd_vnd_signal_value, global_risk_regime,
                 interpretation, geopolitical_shock
          FROM macro_metrics WHERE scan_date = ${scanDate}
        `,
        sql`
          SELECT f.net_value_billion, f.buy_value_billion, f.sell_value_billion,
                 f.signal, f.pattern, f.interpretation,
                 fd.ticker, fd.value_billion, fd.flow_type, fd.rank,
                 fd.buy_value_billion AS fd_buy, fd.sell_value_billion AS fd_sell,
                 fd.net_value_billion AS fd_net, fd.ownership_pct, fd.remaining_room
          FROM foreign_flows f
          LEFT JOIN foreign_flow_details fd ON fd.flow_id = f.id
          WHERE f.scan_date = ${scanDate}
          ORDER BY fd.flow_type, fd.rank
        `,
        sql`
          SELECT sr.rotation_signal, sr.reasoning,
                 srd.classification, s.name AS sector_name, srd.return_pct
          FROM sector_rotations sr
          LEFT JOIN sector_rotation_details srd ON srd.rotation_id = sr.id
          LEFT JOIN sectors s ON srd.sector_id = s.id
          WHERE sr.scan_date = ${scanDate}
        `,
        sql`
          SELECT a.title, a.url, a.domain, a.summary,
                 a.sentiment_score, COALESCE(a.affected_tickers, '{}') AS affected_tickers
          FROM articles a
          JOIN article_searches asrch ON a.search_id = asrch.id
          WHERE asrch.scan_date = ${scanDate}
          ORDER BY a.created_at DESC LIMIT 20
        `,
        getLatestPrices('VNINDEX'),
      ])

    const regimeRow = regimeRows[0]
    const dailyReturn = vnidxPrices
      ? (vnidxPrices.close - vnidxPrices.prev_close) / vnidxPrices.prev_close
      : null
    const regime = regimeRow
      ? {
          regime: regimeRow.regime,
          regime_confidence: regimeRow.regime_confidence,
          key_signal: regimeRow.key_signal,
          recommendation: regimeRow.recommendation,
          vn_index_value: vnidxPrices ? vnidxPrices.close : null,
          vn_index_change_pct: dailyReturn !== null ? dailyReturn * 100 : null,
        }
      : null

    const macroRow = macroRows[0]
    const macro = macroRow
      ? {
          dxy_value: macroRow.dxy_value,
          dxy_change_pct: macroRow.dxy_change_pct,
          dxy_signal: macroRow.dxy_signal_value,
          vix_value: macroRow.vix_value,
          vix_change_pct: macroRow.vix_change_pct,
          vix_signal: macroRow.vix_signal_value,
          usd_vnd_rate: macroRow.usd_vnd_rate,
          usd_vnd_signal: macroRow.usd_vnd_signal_value,
          global_risk_regime: macroRow.global_risk_regime,
          interpretation: macroRow.interpretation,
        }
      : null

    const flowBase = flowRows[0]
    const foreign_flow = flowBase
      ? {
          net_value_billion: flowBase.net_value_billion,
          buy_value_billion: flowBase.buy_value_billion,
          sell_value_billion: flowBase.sell_value_billion,
          signal: flowBase.signal,
          pattern: flowBase.pattern,
          interpretation: flowBase.interpretation,
          top_bought: flowRows
            .filter((r) => r.flow_type === 'bought' && r.ticker)
            .map((r) => ({ ticker: r.ticker, value_billion: r.value_billion, rank: r.rank })),
          top_sold: flowRows
            .filter((r) => r.flow_type === 'sold' && r.ticker)
            .map((r) => ({ ticker: r.ticker, value_billion: r.value_billion, rank: r.rank })),
          holding_details: flowRows
            .filter((r) => r.flow_type === 'holding' && r.ticker)
            .map((r) => ({
              ticker: r.ticker,
              buy_value_billion: r.fd_buy,
              sell_value_billion: r.fd_sell,
              net_value_billion: r.fd_net,
              ownership_pct: r.ownership_pct,
              remaining_room: r.remaining_room,
            })),
        }
      : null

    const rotBase = rotationRows[0]
    const rotation = rotBase
      ? {
          rotation_signal: rotBase.rotation_signal,
          reasoning: rotBase.reasoning,
          hot_sectors: rotationRows
            .filter((r) => r.classification === 'hot')
            .map((r) => ({ sector_name: r.sector_name, return_pct: r.return_pct })),
          cold_sectors: rotationRows
            .filter((r) => r.classification === 'cold')
            .map((r) => ({ sector_name: r.sector_name, return_pct: r.return_pct })),
        }
      : null

    // Read pipeline-resolved shock from macro_metrics (no TS re-resolution needed)
    const geopolitical_shock = (macroRow?.geopolitical_shock as Record<string, unknown>) ?? null

    return {
      scan_date: scanDate,
      regime,
      macro,
      foreign_flow,
      rotation,
      geopolitical_shock,
      articles: articleRows,
    }
  })

const ALERT_STATUS_ORDER: Record<string, number> = {
  triggered: 0,
  active: 1,
  expired: 2,
  cancelled: 3,
}

export const getRecommendations = createServerFn({ method: 'GET' })
  .inputValidator((data: { date: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { date } = data

    const [recordRows, recRows, alertRows] = await Promise.all([
      sql`
        SELECT record_date, total_recs, entry_hit_rate, win_rate,
               best_call, worst_call, key_insight, trading_mode
        FROM daily_records WHERE record_date = ${date}
      `,
      sql`
        SELECT rec.ticker, rec.action, rec.entry_price_vnd, rec.stop_price_vnd,
               rec.target_price_vnd, rec.size_shares, rec.rationale, rec.section,
               rec.strategy, rec.strategy_confidence, rec.risk_reward,
               rec.conservative_target_vnd, rec.aggressive_target_vnd,
               rec.conservative_rr, rec.aggressive_rr,
               rec.source, rec.sim_ev, rec.counter_thesis, rec.verdict,
               ev.entry_hit, ev.stop_hit, ev.target_hit,
               ev.status AS eval_status, ev.pnl_percent, ev.eod_price_vnd, ev.won
        FROM daily_recommendations rec
        JOIN daily_records dr ON rec.record_id = dr.id
        LEFT JOIN daily_evaluations ev ON ev.record_id = dr.id AND ev.ticker = rec.ticker AND ev.section = rec.section
        WHERE dr.record_date = ${date}
        ORDER BY
          CASE rec.section
            WHEN 'MY_HOLDINGS' THEN 1
            WHEN 'TOP_PICKS' THEN 2
            WHEN 'SKIP_THESE' THEN 3
            ELSE 4
          END,
          rec.ticker
      `,
      sql`
        SELECT a.id, a.ticker, a.status,
               ac.condition_type, ac.condition_value,
               a.triggered_values, a.triggered_at, a.priority, a.source,
               a.alert_metadata
        FROM alerts a
        LEFT JOIN alert_conditions ac ON ac.alert_id = a.id AND ac.sort_order = 0
        WHERE a.source_date = ${date}
      `,
    ])

    const record = recordRows[0]
    if (!record) {
      return null
    }

    const alertMap = new Map<string, Record<string, any>[]>()
    for (const a of alertRows) {
      const triggeredValues = a.triggered_values as Record<string, number> | null
      const alert = {
        id: String(a.id),
        status: a.status,
        condition_type: a.condition_type ?? '',
        condition_value: a.condition_value ? Number(a.condition_value) : null,
        triggered_value:
          a.condition_type && triggeredValues?.[a.condition_type as string]
            ? Number(triggeredValues[a.condition_type as string])
            : null,
        triggered_at: a.triggered_at,
        priority: a.priority,
        source: a.source,
        alert_metadata: a.alert_metadata ?? null,
      }
      const list = alertMap.get(a.ticker as string) ?? []
      list.push(alert)
      alertMap.set(a.ticker as string, list)
    }
    for (const [, list] of alertMap) {
      list.sort(
        (a, b) =>
          (ALERT_STATUS_ORDER[a.status as string] ?? 9) -
          (ALERT_STATUS_ORDER[b.status as string] ?? 9),
      )
    }

    const holdingsTickers = new Set(
      recRows.filter((r) => r.section === 'MY_HOLDINGS').map((r) => r.ticker),
    )

    const recommendations = recRows
      .filter((r) => {
        if (r.section === 'WHAT_TO_DO' && holdingsTickers.has(r.ticker)) return false
        return true
      })
      .map((r) => {
        const evaluation = r.eval_status
          ? {
              entry_hit: r.entry_hit ?? false,
              stop_hit: r.stop_hit ?? false,
              target_hit: r.target_hit ?? false,
              status: r.eval_status,
              pnl_percent: r.pnl_percent,
              eod_price_vnd: r.eod_price_vnd,
              won: r.won,
            }
          : null

        return {
          ticker: r.ticker,
          action: r.action,
          entry_price_vnd: r.entry_price_vnd,
          stop_price_vnd: r.stop_price_vnd,
          target_price_vnd: r.target_price_vnd,
          size_shares: r.size_shares,
          rationale: stripAuditTags(r.rationale as string | null),
          section: r.section,
          strategy: r.strategy ?? null,
          strategy_confidence: r.strategy_confidence ?? null,
          risk_reward: r.risk_reward ?? null,
          conservative_target_vnd: r.conservative_target_vnd ?? null,
          aggressive_target_vnd: r.aggressive_target_vnd ?? null,
          conservative_rr: r.conservative_rr ?? null,
          aggressive_rr: r.aggressive_rr ?? null,
          source: r.source ?? null,
          sim_ev: r.sim_ev ?? null,
          counter_thesis: r.counter_thesis ?? null,
          verdict: stripAuditTags(r.verdict as string | null),
          evaluation,
          alerts: alertMap.get(r.ticker as string) ?? [],
        }
      })

    return {
      record_date: record.record_date,
      total_recs: record.total_recs,
      entry_hit_rate: record.entry_hit_rate,
      win_rate: record.win_rate,
      best_call: record.best_call,
      worst_call: record.worst_call,
      key_insight: record.key_insight,
      trading_mode: record.trading_mode,
      recommendations,
    }
  })

export const getMiddayCheck = createServerFn({ method: 'GET' })
  .inputValidator((data: { date: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { date } = data

    const checkRows = await sql`
      SELECT id, trading_mode, morning_reflection, afternoon_plan, capital_note,
             recommendation_overrides
      FROM midday_checks WHERE scan_date = ${date}
    `

    if (checkRows.length === 0) {
      return null
    }

    const check = checkRows[0]

    const [entriesRows, moversRows, alertsRows, morningAlertsRows] = await Promise.all([
      sql`
        SELECT ticker, recommended_entry_vnd, actual_low_vnd, current_price_vnd, status
        FROM midday_entries_hit WHERE midday_id = ${check.id}
      `,
      sql`
        SELECT ticker, open_price_vnd, current_price_vnd, change_pct, direction
        FROM midday_big_movers WHERE midday_id = ${check.id}
        ORDER BY ABS(change_pct) DESC
      `,
      sql`
        SELECT ticker, current_price_vnd, level_vnd, level_type, distance_pct, urgency
        FROM midday_position_alerts WHERE midday_id = ${check.id}
        ORDER BY
          CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
      `,
      sql`
        SELECT ticker, action, urgency, reason,
               target_price, stop_price, consensus, dissenting_views,
               entry_price, pct_from_entry, weight_pct, volume_signal
        FROM morning_position_alerts
        WHERE scan_date = ${date}
        ORDER BY
          CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
          ticker
      `.catch(() => []),
    ])

    const afternoonPlanRaw = Array.isArray(check.afternoon_plan) ? check.afternoon_plan : []
    const afternoonPlanProse = formatAfternoonPlanProse(afternoonPlanRaw, null)

    return {
      trading_mode: check.trading_mode,
      morning_reflection: check.morning_reflection,
      afternoon_plan: afternoonPlanProse,
      afternoon_plan_raw: afternoonPlanRaw,
      capital_note: check.capital_note,
      entries_hit: entriesRows,
      big_movers: moversRows,
      position_alerts: alertsRows,
      morning_position_alerts: morningAlertsRows,
      recommendation_overrides: check.recommendation_overrides ?? [],
    }
  })

export const getIntelLearnings = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()

  const [summaryRows, patternRows, sectorRows, tickerRows] = await Promise.all([
    sql`
      SELECT total_days, total_recs, overall_entry_hit_rate, overall_win_rate, avg_pnl_percent
      FROM learnings_summary ORDER BY last_updated DESC LIMIT 1
    `,
    sql`
      SELECT pattern_type, pattern_description, win_rate, loss_rate,
             sample_size, actionable_rule, avoid_rule
      FROM learning_patterns
      ORDER BY sample_size DESC NULLS LAST
    `,
    sql`
      SELECT s.name AS sector_name, si.bias, si.win_rate
      FROM sector_insights si
      JOIN sectors s ON si.sector_id = s.id
      ORDER BY si.win_rate DESC NULLS LAST
    `,
    sql`
      SELECT ticker, recent_accuracy
      FROM ticker_insights
      ORDER BY recent_accuracy DESC NULLS LAST
    `,
  ])

  return {
    summary: summaryRows[0] ?? null,
    winning_patterns: patternRows
      .filter((r) => r.pattern_type === 'winning')
      .map((r) => ({
        description: r.pattern_description,
        win_rate: r.win_rate,
        loss_rate: r.loss_rate,
        sample_size: r.sample_size,
        actionable_rule: r.actionable_rule,
        avoid_rule: r.avoid_rule,
      })),
    losing_patterns: patternRows
      .filter((r) => r.pattern_type === 'losing')
      .map((r) => ({
        description: r.pattern_description,
        win_rate: r.win_rate,
        loss_rate: r.loss_rate,
        sample_size: r.sample_size,
        actionable_rule: r.actionable_rule,
        avoid_rule: r.avoid_rule,
      })),
    sector_insights: sectorRows,
    ticker_insights: tickerRows,
  }
})
