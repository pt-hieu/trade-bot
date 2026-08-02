"use client";

import type { PortfolioSnapshot, TradeEvent } from "../../types/index";
import { formatVND } from "../../lib/utils";
import { formatShortDate } from "../../lib/date";

interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: PortfolioSnapshot & { _trades?: TradeEvent[] } }>;
}

export function ChartTooltip({ active, payload }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  const trades = data._trades;

  return (
    <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-muted-foreground mb-1">
        {formatShortDate(data.snapshot_date)}
      </p>
      <p className="font-semibold text-sm font-mono tabular-nums">
        {formatVND(Number(data.invested_value_vnd))}
      </p>
      {trades && trades.length > 0 && (
        <div className="mt-1.5 pt-1.5 border-t border-border/30 space-y-0.5">
          {trades.map((t, i) => (
            <p
              key={i}
              className={`text-xs font-medium ${
                t.action === "BUY" ? "text-emerald-500" : "text-rose-500"
              }`}
            >
              {t.action} {t.ticker} ({t.shares} shares)
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
