import type { PortfolioSnapshot, TradeEvent } from "../../types/index";

export function enrichTradesWithValue(
  trades: TradeEvent[],
  snapshots: PortfolioSnapshot[],
): Array<TradeEvent & { value: number }> {
  const snapshotMap = new Map(
    snapshots.map((snapshot) => [snapshot.snapshot_date, Number(snapshot.invested_value_vnd)]),
  );

  return trades
    .map((trade) => {
      const value = snapshotMap.get(trade.date);
      if (value === undefined) return null;
      return { ...trade, value };
    })
    .filter(Boolean) as Array<TradeEvent & { value: number }>;
}

export function groupTradesByDate(
  trades: Array<TradeEvent & { value: number }>,
) {
  const grouped = new Map<string, Array<TradeEvent & { value: number }>>();
  for (const trade of trades) {
    const existing = grouped.get(trade.date) ?? [];
    existing.push(trade);
    grouped.set(trade.date, existing);
  }
  return grouped;
}

interface TradeMarkerProps {
  cx?: number;
  cy?: number;
  trades: TradeEvent[];
}

export function TradeMarkerDot({ cx, cy, trades }: TradeMarkerProps) {
  if (!cx || !cy) return null;

  const hasBuy = trades.some((trade) => trade.action === "BUY");
  const hasSell = trades.some((trade) => trade.action === "SELL");
  const color = hasBuy && hasSell ? "#f59e0b" : hasBuy ? "#10b981" : "#f43f5e";

  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={5}
        fill={color}
        stroke="hsl(var(--background))"
        strokeWidth={2}
      />
    </g>
  );
}
