/**
 * Research domain tools — articles, financials, company research, valuation.
 */
import { z } from 'zod'
import type { Tool } from 'ai'
import { getSql, VNSTOCK_API_URL, TAVILY_API_KEY } from './shared'

// ─── Search Articles ──────────────────────────────────────────────────────────

const search_articles: Tool = {
  description:
    'Search recent news articles by keyword or ticker. Returns titles, summaries, and sentiment. Use for catalysts, news flow, and market narrative.',
  inputSchema: z.object({
    query: z.string().describe('Search keyword or ticker, e.g. "FPT AI" or "VHM bond"'),
    limit: z.number().optional().describe('Max results (default: 10)'),
  }),
  execute: async (input: { query: string; limit?: number }) => {
    const sql = getSql()
    const limit = input.limit ?? 10
    const rows = await sql`
      SELECT id, title, domain AS source, scraped_at AS published_at,
             sentiment_score AS sentiment, summary
      FROM articles
      WHERE to_tsvector('simple', title || ' ' || COALESCE(summary, '')) @@ plainto_tsquery('simple', ${input.query})
         OR affected_tickers @> ARRAY[${input.query.toUpperCase()}]
      ORDER BY scraped_at DESC
      LIMIT ${limit}
    `
    return JSON.stringify(rows)
  },
}

// ─── Read Articles (batch) ────────────────────────────────────────────────────

const read_articles: Tool = {
  description:
    'Read summaries of multiple articles by their UUIDs in one call. Articles without summaries are flagged.',
  inputSchema: z.object({
    ids: z
      .array(z.string().uuid())
      .min(1)
      .max(10)
      .describe('Article UUIDs from search_articles results'),
  }),
  execute: async (input: { ids: string[] }) => {
    const sql = getSql()
    const rows = await sql`
      SELECT id, title, domain AS source, scraped_at AS published_at,
             COALESCE(summary, '(summary not available)') AS content,
             sentiment_score AS sentiment
      FROM articles
      WHERE id = ANY(${input.ids}::uuid[])
    `
    return JSON.stringify(rows)
  },
}

// ─── Financial Ratios ─────────────────────────────────────────────────────────

const get_financials: Tool = {
  description:
    'Get key financial ratios for a ticker: PE, PB, ROE, ROA, gross margin, debt/equity, revenue growth. From latest quarterly report.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol'),
  }),
  execute: async (input: { ticker: string }) => {
    const apiUrl = VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    try {
      const url = new URL(`${apiUrl}/financials/ratios`)
      url.searchParams.set('symbol', input.ticker.toUpperCase())
      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(15_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      return JSON.stringify(await res.json())
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Company Research ─────────────────────────────────────────────────────────

const get_company_research: Tool = {
  description:
    'Get internal research notes for a longterm watchlist stock — investment thesis, entry zones, conviction level, and last review date.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol'),
  }),
  execute: async (input: { ticker: string }) => {
    const sql = getSql()
    const rows = await sql`
      SELECT lw.ticker, lw.conviction, lw.entry_zone_vnd,
             lw.last_reviewed_at, cr.sections, cr.updated_at
      FROM longterm_watchlist lw
      LEFT JOIN company_research cr ON cr.ticker = lw.ticker
      WHERE lw.ticker = ${input.ticker.toUpperCase()}
        AND lw.is_active = TRUE
    `
    return JSON.stringify(rows[0] ?? null)
  },
}

// ─── Valuation History ────────────────────────────────────────────────────────

const get_valuation_history: Tool = {
  description:
    'Get 8-quarter historical PE/PB percentiles, zone classification (CHEAP/FAIR/EXPENSIVE/EXTREME_HIGH), and EPS/margin trajectory for a stock. Use to assess whether current valuation is historically stretched or attractive.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol, e.g. FPT'),
  }),
  execute: async (input: { ticker: string }) => {
    const apiUrl = VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    try {
      const url = new URL(`${apiUrl}/financials/valuation-history`)
      url.searchParams.set('symbol', input.ticker.toUpperCase())
      url.searchParams.set('periods', '8')
      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(20_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      return JSON.stringify(await res.json())
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Earnings Quality ─────────────────────────────────────────────────────────

const get_earnings_quality: Tool = {
  description:
    'Decompose 4 quarters of earnings into core operating income vs non-core (financial income, asset revaluation, JV gains). Returns quality grade (HIGH/MEDIUM/LOW) and core ratio trend. Essential for Vietnamese BDS/real estate stocks.',
  inputSchema: z.object({
    ticker: z.string().describe('Stock ticker symbol, e.g. DIG'),
  }),
  execute: async (input: { ticker: string }) => {
    const apiUrl = VNSTOCK_API_URL
    if (!apiUrl) return JSON.stringify({ error: 'VNSTOCK_API_URL not configured' })

    try {
      const url = new URL(`${apiUrl}/financials/earnings-quality`)
      url.searchParams.set('symbol', input.ticker.toUpperCase())
      url.searchParams.set('periods', '4')
      const res = await fetch(url.toString(), { signal: AbortSignal.timeout(20_000) })
      if (!res.ok) return JSON.stringify({ error: `API returned ${res.status}` })
      return JSON.stringify(await res.json())
    } catch (e) {
      return JSON.stringify({ error: String(e) })
    }
  },
}

// ─── Web Search ──────────────────────────────────────────────────────────────

const _webSearchSchema = z.object({
  query: z
    .string()
    .describe('Search query for web news, geopolitical events, or market-moving information'),
  max_results: z.number().optional().describe('Max results to return (default: 5, max: 10)'),
})

const web_search: Tool = {
  description:
    'Search the web for recent news, geopolitical events, macro developments, or any information not in internal DB. Use for world events (wars, sanctions, trade deals), global market moves, or questions outside Vietnamese stock news.',
  inputSchema: _webSearchSchema,
  execute: async (input: z.infer<typeof _webSearchSchema>) => {
    const apiKey = TAVILY_API_KEY
    if (!apiKey) return JSON.stringify({ error: 'Web search not configured (TAVILY_API_KEY missing)' })

    try {
      const res = await fetch('https://api.tavily.com/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKey,
          query: input.query,
          max_results: Math.min(input.max_results ?? 5, 10),
          search_depth: 'basic',
          include_answer: true,
          include_raw_content: false,
        }),
        signal: AbortSignal.timeout(15_000),
      })
      if (!res.ok) return JSON.stringify({ error: `Search API returned ${res.status}` })

      const data = await res.json()
      return JSON.stringify({
        answer: data.answer ?? null,
        results: (data.results ?? []).map((r: Record<string, unknown>) => ({
          title: r.title,
          url: r.url,
          content: r.content,
          published_date: r.published_date ?? null,
        })),
      })
    } catch (e) {
      return JSON.stringify({ error: `Web search failed: ${String(e)}` })
    }
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export const researchTools = {
  search_articles,
  read_articles,
  get_financials,
  get_company_research,
  get_valuation_history,
  get_earnings_quality,
  web_search,
}
