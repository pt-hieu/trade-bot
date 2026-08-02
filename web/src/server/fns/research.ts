import { createServerFn } from '@tanstack/react-start'
import { getSql } from '../db'
import type { CompanyResearch } from '../../types'

export const getCompanyResearch = createServerFn({ method: 'GET' })
  .inputValidator((data: { ticker: string }) => data)
  .handler(async ({ data }) => {
    const sql = getSql()
    const upperTicker = data.ticker.toUpperCase()

    const rows = await sql`
      SELECT
        ticker, sections, research_date,
        auto_generated, version, updated_at
      FROM company_research
      WHERE ticker = ${upperTicker}
      ORDER BY version DESC
      LIMIT 1
    `

    if (!rows.length) {
      return null
    }

    return rows[0] as CompanyResearch
  })
