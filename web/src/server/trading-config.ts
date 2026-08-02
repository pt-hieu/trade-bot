import { getSql } from './db'

let _transactionCostPct: number | null = null

export async function getTransactionCostPct(): Promise<number> {
  if (_transactionCostPct !== null) return _transactionCostPct

  try {
    const sql = getSql()
    const rows = await sql`
      SELECT transaction_cost_pct FROM trading_config LIMIT 1
    `
    _transactionCostPct = (rows[0]?.transaction_cost_pct as number) ?? 0.003
  } catch {
    _transactionCostPct = 0.003
  }

  return _transactionCostPct
}

export function clearTradingConfigCache(): void {
  _transactionCostPct = null
}
