"""L1 of the 2026-04-24 regime fix — post-parallel regime adjustment.

Extracted from ``phase_parallel`` to keep that module under the
300-350-line cap. Runs after ``macro_metrics`` and ``foreign_flow``
have both returned from Phase 1's ``asyncio.gather`` and writes the
adjusted regime back onto ``macro_metrics`` in place.
"""

from __future__ import annotations

from asyncio import Task

from shared.errors import report_caught
from shared.rules.local_regime_adjustment import apply_local_vn_adjustment


async def resolve_vn_index_trend(task: Task[float | None], scan_date: object) -> float | None:
    """Await the VN-Index 3d task, fail-closed to None on any error."""
    try:
        return await task
    except Exception as error:
        report_caught(
            name="phase_parallel.local_regime_adjustment",
            exc=error,
            scan_date=str(scan_date),
            step="vn_index_trend_3d",
        )
        return None


def apply_local_regime_adjustment(
    results_dict: dict[str, object],
    vn_index_3d_pct: float | None,
) -> None:
    """Merge macro_metrics + foreign_flow into the final regime label.

    Reads the foreign-flow signal / breadth ratio off the already-
    fetched foreign_flow + macro payloads, hands them to
    ``apply_local_vn_adjustment`` along with the pre-fetched VN-Index
    3d trend, and mutates ``macro_metrics`` in place. Records the rules
    fired under ``macro_metrics['regime_adjustments']`` for audit.

    Fails safe — on any missing input the global regime stands and the
    adjustments list stays empty.
    """
    macro = results_dict.get("macro_metrics")
    if not isinstance(macro, dict):
        return
    if not isinstance(macro.get("global_risk_regime"), str):
        return

    flow = results_dict.get("foreign_flow")
    foreign_flow_signal: str | None = None
    if isinstance(flow, dict):
        signal_value = flow.get("signal")
        foreign_flow_signal = str(signal_value) if signal_value is not None else None

    breadth_ratio = macro.get("breadth_ratio")

    adjusted_regime, rules = apply_local_vn_adjustment(
        computed_regime=str(macro.get("global_risk_regime") or "CAUTIOUS"),
        vix_signal=str(macro.get("vix_signal") or ""),
        usd_vnd_signal=str(macro.get("usd_vnd_signal") or ""),
        foreign_flow_signal=foreign_flow_signal,
        breadth_ratio=float(breadth_ratio) if isinstance(breadth_ratio, (int, float)) else None,
        vn_index_3d_pct=vn_index_3d_pct,
    )

    macro["regime_adjustments"] = rules
    if rules:
        print(
            "  [Macro] Local VN adjustment: {} -> {} ({})".format(
                macro.get("global_risk_regime"),
                adjusted_regime,
                ", ".join(rules),
            ),
            flush=True,
        )
        macro["global_risk_regime"] = adjusted_regime


__all__ = ["apply_local_regime_adjustment"]
