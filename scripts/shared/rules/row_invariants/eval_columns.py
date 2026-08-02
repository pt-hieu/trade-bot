"""Single source of truth for daily_evaluations INSERT column order (SWI-NN).

`INSERT_EVAL_SQL` in `shared.neon.insert_records._common` lists the same
columns positionally; the row_invariants mirror reads them via index. A
length-parity unit test (`test_row_invariants.py::TestEvalColumnsSqlParity`)
fails the build if the two drift. Lives under `row_invariants` (its primary
consumer) so the neon package stays a clean public seam.
"""

from __future__ import annotations

EVAL_COLUMNS: tuple[str, ...] = (
    "record_id",
    "ticker",
    "recommendation",
    "section",
    "entry_hit",
    "stop_hit",
    "target_hit",
    "eod_price_vnd",
    "pnl_percent",
    "status",
    "analysis",
    "won",
    "day_change",
    "entry_gap_pct",
    "predicted_rr",
    "actual_max_rr",
    "stop_buffer_pct",
    "stop_vs_atr_ratio",
    "atr_pct",
    "trade_executed",
    "actual_exit_price_vnd",
    "actual_pl_pct",
    "actual_pl_net_vnd",
    "strategy",
    "plan_type",
    "rule_applied",
    "stop_price_vnd",
)

TICKER_IDX = EVAL_COLUMNS.index("ticker")
RULE_APPLIED_IDX = EVAL_COLUMNS.index("rule_applied")
STOP_PRICE_VND_IDX = EVAL_COLUMNS.index("stop_price_vnd")
