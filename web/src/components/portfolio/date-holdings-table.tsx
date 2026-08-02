"use client";

import type { DateHolding } from "../../types/index";
import { formatCompact } from "../../lib/utils";

export function DateHoldingsTable({ holdings }: { holdings: DateHolding[] }) {
  if (!holdings.length) return null;

  const totalValue = holdings.reduce(
    (sum, h) => sum + Number(h.market_value_vnd),
    0,
  );

  return (
    <div className="rounded-md border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-muted-foreground text-xs">
            <th className="text-left px-4 py-2 font-medium">Ticker</th>
            <th className="text-left px-4 py-2 font-medium">Plan</th>
            <th className="text-right px-4 py-2 font-medium">Shares</th>
            <th className="text-right px-4 py-2 font-medium">Close Price</th>
            <th className="text-right px-4 py-2 font-medium">Value</th>
            <th className="text-right px-4 py-2 font-medium">Weight</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const weight =
              totalValue > 0
                ? `${((Number(h.market_value_vnd) / totalValue) * 100).toFixed(1)}%`
                : "-";

            return (
              <tr
                key={`${h.ticker}-${h.plan_type}`}
                className="border-b last:border-0"
                data-test-id={`date-holding-row-${h.ticker}`}
              >
                <td className="px-4 py-2.5 font-medium">{h.ticker}</td>
                <td className="px-4 py-2.5 text-muted-foreground text-xs">
                  {h.plan_type}
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                  {Number(h.shares).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                  {Number(h.close_vnd).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                  {formatCompact(Number(h.market_value_vnd))}
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-muted-foreground">
                  {weight}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
