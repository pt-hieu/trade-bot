import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { parseJsonb } from './neon-utils'
import type { RotationPatterns, MacroPatterns } from '../../types/learnings'

export const getLearnings = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()

  const [
    summaryRows,
    patternRows,
    sectorRows,
    tickerRows,
    calibrationRows,
    middayRows,
    tradingModeRows,
    rotationRows,
    macroRows,
    strategyRows,
    rulesRows,
  ] = await Promise.all([
    sql`
      SELECT total_days, total_recs, overall_entry_hit_rate, overall_win_rate,
             avg_pnl_percent, last_updated
      FROM learnings_summary ORDER BY last_updated DESC LIMIT 1
    `,
    sql`
      SELECT pattern_type, pattern_description, win_rate, loss_rate,
             sample_size, actionable_rule, avoid_rule, dominant_error
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
    sql`
      SELECT avg_entry_gap_pct, pct_entries_unreachable, avg_stop_vs_atr,
             pct_stops_too_tight, avg_predicted_rr, avg_actual_rr, target_hit_rate, sample_size
      FROM calibration_insights
      ORDER BY scan_date DESC LIMIT 1
    `,
    sql`
      SELECT days_with_midday, adjustment_win_rate, when_helpful, when_harmful, average_improvement
      FROM midday_patterns LIMIT 1
    `,
    sql`
      SELECT mode_compliance_rate, mode_violations, mode_appropriate_win_rate
      FROM trading_mode_patterns LIMIT 1
    `,
    sql`
      SELECT rp.id, rp.total_days, rp.overall_accuracy, rp.hot_hit_rate, rp.cold_hit_rate,
             rp.avg_hot_vs_market, rp.avg_cold_vs_market,
             rss.as_hot_accuracy, rss.as_cold_accuracy,
             s.name AS sector_name
      FROM rotation_patterns rp
      LEFT JOIN rotation_sector_scores rss ON rss.pattern_id = rp.id
      LEFT JOIN sectors s ON rss.sector_id = s.id
      ORDER BY rp.updated_at DESC
    `,
    sql`
      SELECT mp.id, mp.total_days, mp.overall_accuracy, mp.false_alarms, mp.missed_drops,
             mp.missed_opportunities,
             mra.regime, mra.days_count, mra.correct_count, mra.avg_vn_change
      FROM macro_patterns mp
      LEFT JOIN macro_regime_accuracy mra ON mra.pattern_id = mp.id
      ORDER BY mp.updated_at DESC
    `,
    sql`
      SELECT strategy, win_rate, sample_size
      FROM strategy_insights
      WHERE scan_date = (SELECT MAX(scan_date) FROM strategy_insights)
      ORDER BY sample_size DESC NULLS LAST
    `,
    sql`
      SELECT rule_name, description, action, confidence, sample_size, expires_at
      FROM trading_rules
      WHERE rule_type = 'avoid'
        AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)
      ORDER BY confidence DESC
      LIMIT 5
    `,
  ])

  const calibration = calibrationRows[0] ?? null

  const midday = middayRows[0]
    ? {
        days_with_midday: middayRows[0].days_with_midday,
        adjustment_win_rate: middayRows[0].adjustment_win_rate,
        when_helpful: parseJsonb<string[]>(middayRows[0].when_helpful, []),
        when_harmful: parseJsonb<string[]>(middayRows[0].when_harmful, []),
        average_improvement: middayRows[0].average_improvement,
      }
    : null

  const trading_mode = tradingModeRows[0]
    ? {
        mode_compliance_rate: tradingModeRows[0].mode_compliance_rate,
        mode_violations: parseJsonb<string[]>(tradingModeRows[0].mode_violations, []),
        mode_appropriate_win_rate: tradingModeRows[0].mode_appropriate_win_rate,
      }
    : null

  let rotation: RotationPatterns | null = null
  if (rotationRows.length > 0) {
    const first = rotationRows[0]
    rotation = {
      total_days: first.total_days,
      overall_accuracy: first.overall_accuracy,
      hot_hit_rate: first.hot_hit_rate,
      cold_hit_rate: first.cold_hit_rate,
      avg_hot_vs_market: first.avg_hot_vs_market,
      avg_cold_vs_market: first.avg_cold_vs_market,
      sector_scores: rotationRows
        .filter((row) => row.sector_name != null)
        .map((row) => ({
          sector_name: row.sector_name as string,
          as_hot_accuracy: row.as_hot_accuracy,
          as_cold_accuracy: row.as_cold_accuracy,
        })),
    }
  }

  let macro: MacroPatterns | null = null
  if (macroRows.length > 0) {
    const first = macroRows[0]
    macro = {
      total_days: first.total_days,
      overall_accuracy: first.overall_accuracy,
      false_alarms: first.false_alarms,
      missed_drops: first.missed_drops,
      missed_opportunities: first.missed_opportunities,
      regime_accuracy: macroRows
        .filter((row) => row.regime != null)
        .map((row) => ({
          regime: row.regime as string,
          days_count: row.days_count,
          correct_count: row.correct_count,
          avg_vn_change: row.avg_vn_change,
        })),
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Neon driver returns untyped rows
  const mapPattern = (row: any) => ({
    description: row.pattern_description as string,
    win_rate: row.win_rate,
    loss_rate: row.loss_rate,
    sample_size: row.sample_size,
    actionable_rule: row.actionable_rule,
    avoid_rule: row.avoid_rule,
    dominant_error: row.dominant_error && row.dominant_error !== 'N/A' ? row.dominant_error : null,
  })

  return {
    summary: summaryRows[0] ?? null,
    winning_patterns: patternRows.filter((row) => row.pattern_type === 'winning').map(mapPattern),
    losing_patterns: patternRows.filter((row) => row.pattern_type === 'losing').map(mapPattern),
    sector_insights: sectorRows,
    ticker_insights: tickerRows,
    calibration,
    midday,
    trading_mode,
    rotation,
    macro,
    strategy_insights: strategyRows.map((row) => ({
      strategy: row.strategy as string,
      win_rate: row.win_rate,
      sample_size: row.sample_size,
    })),
    trading_rules: rulesRows.map((row) => ({
      rule_name: row.rule_name as string,
      description: row.description as string,
      action: row.action as string,
      confidence: row.confidence,
      sample_size: row.sample_size,
      expires_at: row.expires_at,
    })),
    trends: [],
  }
})
