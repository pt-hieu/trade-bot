"""Pipeline data validation — pre-Phase 2 checks."""

from shared.errors import report_caught


def validate_pipeline_data(
    technicals,
    cash_balance: float,
    holdings: list[dict],
    phase1_macro_metrics: dict | None,
) -> None:
    """Validate pipeline data before Phase 2 (non-fatal).

    Args:
        technicals: Ticker-keyed dict or list with ticker field.
        cash_balance: Total cash in VND.
        holdings: list[HoldingData] — one row per (ticker, plan_type) slice
            per migration 314. The inner validator iterates slices directly.
        phase1_macro_metrics: macro_metrics dict (or None) from Phase 1.
    """
    try:
        from agents.tools.validation import validate_pipeline_data as _validate

        tech_dict = (
            {row["ticker"]: row for row in technicals}
            if isinstance(technicals, list)
            else technicals
        )
        report = _validate(
            technicals=tech_dict,
            cash_balance=cash_balance,
            holdings=holdings,
            macro=phase1_macro_metrics,
        )
        if report.has_issues:
            report.log()
        else:
            print("  [Validation] All data checks passed", flush=True)
    except Exception as e:
        report_caught("pipeline.validation", e)
