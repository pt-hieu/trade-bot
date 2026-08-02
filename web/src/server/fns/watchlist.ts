import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import { fetchRsi } from '../vnstock'

// ─── Types ────────────────────────────────────────────────────────────────────

type WatchlistType = 'swing' | 'longterm'

type StockType =
  | 'Private' | 'State' | 'Industrial' | 'Vingroup' | 'Retail'
  | 'Securities' | 'Conglomerate' | 'Energy' | 'Commodities'
  | 'Aviation' | 'Insurance' | 'Beverages' | 'Dairy' | 'Logistics' | 'Steel'

type ConvictionLevel = 'High' | 'Medium-High' | 'Medium' | 'Medium-Low' | 'Low'

interface WatchlistGetParams {
  type?: WatchlistType
}

interface WatchlistAddInput {
  ticker: string
  type: WatchlistType
  sector_name: string
  stock_type?: StockType
  is_pinned?: boolean
  pin_reason?: string
  entry_zone_vnd?: number
  conviction?: ConvictionLevel
  tier?: number
  notes?: string
}

interface WatchlistEditInput {
  ticker: string
  type: WatchlistType
  stock_type?: StockType
  is_pinned?: boolean
  pin_reason?: string | null
  conviction?: ConvictionLevel
  tier?: number
  entry_zone_vnd?: number
  notes?: string | null
}

interface WatchlistRefreshRsiInput {
  ticker: string
}

interface WatchlistRemoveInput {
  ticker: string
  type: WatchlistType
}

// ─── GET /watchlist ────────────────────────────────────────────────────────────

export const getWatchlist = createServerFn({ method: 'GET' })
  .inputValidator((data: WatchlistGetParams) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const type = data.type ?? 'swing'

    if (type === 'longterm') {
      const rows = await sql`
        SELECT
          lw.id, lw.ticker, s.name AS sector_name, lw.entry_zone_vnd,
          lw.conviction, lw.pe_ratio, lw.roe, lw.dividend_yield,
          lw.tier, lw.notes, lw.created_at, lw.updated_at,
          lw.entry_zone_method, lw.conviction_score, lw.conviction_method,
          COALESCE(lw.review_flags, '{}') AS review_flags, lw.last_reviewed_at
        FROM longterm_watchlist lw
        JOIN sectors s ON lw.sector_id = s.id
        WHERE lw.is_active = TRUE
        ORDER BY lw.tier ASC NULLS LAST, s.name, lw.ticker
      `
      return rows
    }

    const rows = await sql`
      SELECT
        sw.id, sw.ticker, s.name AS sector_name, sw.stock_type,
        sw.rsi, sw.notes, sw.is_pinned, sw.pin_reason,
        sw.created_at, sw.updated_at
      FROM swing_watchlist sw
      JOIN sectors s ON sw.sector_id = s.id
      WHERE sw.is_active = TRUE
      ORDER BY s.name, sw.ticker
    `
    return rows
  })

// ─── GET /watchlist/sectors ────────────────────────────────────────────────────

export const getWatchlistSectors = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  const rows = await sql`
    SELECT id, name, display_name
    FROM sectors
    ORDER BY name
  `
  return rows
})

// ─── POST /watchlist ───────────────────────────────────────────────────────────

export const addToWatchlist = createServerFn({ method: 'POST' })
  .inputValidator((data: WatchlistAddInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { ticker, type, sector_name, ...rest } = data
    const upperTicker = ticker.toUpperCase()

    const [sectorResult, rsiResult] = await Promise.allSettled([
      sql`SELECT id FROM sectors WHERE LOWER(name) = LOWER(${sector_name})`,
      type === 'swing' ? fetchRsi(upperTicker) : Promise.resolve(null),
    ])

    if (sectorResult.status === 'rejected') throw sectorResult.reason
    const sectors = sectorResult.value
    if (!sectors.length) {
      throw new Error(`Sector not found: ${sector_name}`)
    }
    const sectorId = sectors[0].id
    const rsi = rsiResult.status === 'fulfilled' ? rsiResult.value : null

    if (type === 'longterm') {
      const conviction = rest.conviction || 'Medium'
      const entryZone = rest.entry_zone_vnd ?? null
      const tier = rest.tier ?? null
      const notes = rest.notes || null

      const rows = await sql`
        INSERT INTO longterm_watchlist (ticker, sector_id, entry_zone_vnd, conviction, tier, notes, is_active)
        VALUES (${upperTicker}, ${sectorId}, ${entryZone}, ${conviction}, ${tier}, ${notes}, TRUE)
        ON CONFLICT (ticker) DO UPDATE SET
          is_active = TRUE,
          sector_id = EXCLUDED.sector_id,
          entry_zone_vnd = EXCLUDED.entry_zone_vnd,
          conviction = EXCLUDED.conviction,
          tier = EXCLUDED.tier,
          notes = EXCLUDED.notes,
          updated_at = NOW()
        RETURNING id, ticker
      `
      return rows[0]
    }

    const stockType = rest.stock_type || 'Private'
    const isPinned = rest.is_pinned ?? false
    const pinReason = rest.pin_reason || null
    const notes = rest.notes || null

    const rows = await sql`
      INSERT INTO swing_watchlist (ticker, sector_id, stock_type, rsi, is_pinned, pin_reason, notes, is_active)
      VALUES (${upperTicker}, ${sectorId}, ${stockType}, ${rsi}, ${isPinned}, ${pinReason}, ${notes}, TRUE)
      ON CONFLICT (ticker) DO UPDATE SET
        is_active = TRUE,
        sector_id = EXCLUDED.sector_id,
        stock_type = EXCLUDED.stock_type,
        rsi = COALESCE(EXCLUDED.rsi, swing_watchlist.rsi),
        is_pinned = EXCLUDED.is_pinned,
        pin_reason = EXCLUDED.pin_reason,
        notes = EXCLUDED.notes,
        updated_at = NOW()
      RETURNING id, ticker, rsi
    `
    return rows[0]
  })

// ─── PATCH /watchlist (refresh RSI) ───────────────────────────────────────────

export const refreshWatchlistRsi = createServerFn({ method: 'POST' })
  .inputValidator((data: WatchlistRefreshRsiInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const upperTicker = data.ticker.toUpperCase()
    const rsi = await fetchRsi(upperTicker)

    if (rsi === null) {
      throw new Error('Could not fetch RSI — vnstock API unavailable')
    }

    await sql`
      UPDATE swing_watchlist SET rsi = ${rsi}, updated_at = NOW()
      WHERE ticker = ${upperTicker} AND is_active = TRUE
    `

    return { ticker: upperTicker, rsi }
  })

// ─── PUT /watchlist ────────────────────────────────────────────────────────────

export const updateWatchlistItem = createServerFn({ method: 'POST' })
  .inputValidator((data: WatchlistEditInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { ticker, type, ...fields } = data
    const upperTicker = ticker.toUpperCase()

    if (type === 'longterm') {
      const rows = await sql`
        UPDATE longterm_watchlist SET
          conviction = COALESCE(${fields.conviction ?? null}, conviction),
          tier = COALESCE(${fields.tier ?? null}, tier),
          entry_zone_vnd = COALESCE(${fields.entry_zone_vnd ?? null}, entry_zone_vnd),
          notes = ${fields.notes ?? null},
          updated_at = NOW()
        WHERE ticker = ${upperTicker} AND is_active = TRUE
        RETURNING id, ticker
      `
      if (!rows.length) {
        throw new Error('Ticker not found')
      }
      return rows[0]
    }

    const isPinned = fields.is_pinned ?? null
    const pinReason = fields.pin_reason ?? null

    const rows = await sql`
      UPDATE swing_watchlist SET
        stock_type = COALESCE(${fields.stock_type ?? null}, stock_type),
        is_pinned = COALESCE(${isPinned}, is_pinned),
        pin_reason = ${isPinned === false ? null : pinReason},
        notes = ${fields.notes ?? null},
        updated_at = NOW()
      WHERE ticker = ${upperTicker} AND is_active = TRUE
      RETURNING id, ticker
    `
    if (!rows.length) {
      throw new Error('Ticker not found')
    }
    return rows[0]
  })

// ─── DELETE /watchlist ─────────────────────────────────────────────────────────

export const removeFromWatchlist = createServerFn({ method: 'POST' })
  .inputValidator((data: WatchlistRemoveInput) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const { ticker, type } = data
    const upperTicker = ticker.toUpperCase()

    if (type === 'swing') {
      const pinCheck = await sql`
        SELECT is_pinned, pin_reason
        FROM swing_watchlist
        WHERE ticker = ${upperTicker} AND is_active = TRUE
      `
      if (pinCheck.length && pinCheck[0].is_pinned) {
        return {
          removed: false,
          pinned: true,
          reason: (pinCheck[0].pin_reason as string) || 'Stock is pinned',
        }
      }
    }

    if (type === 'longterm') {
      await sql`
        UPDATE longterm_watchlist
        SET is_active = FALSE, updated_at = NOW()
        WHERE ticker = ${upperTicker}
      `
    } else {
      await sql`
        UPDATE swing_watchlist
        SET is_active = FALSE, updated_at = NOW()
        WHERE ticker = ${upperTicker} AND (is_pinned = FALSE OR is_pinned IS NULL)
      `
    }

    return { removed: true }
  })
