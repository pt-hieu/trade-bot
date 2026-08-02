"""Build SKIP_THESE recommendation rows from the shared skip_selector.

Extracted from `recommendation_builder.py` to keep that file under the
300-350 line cap (CLAUDE.md). The SKIP-rec construction needs full access
to the sector/gated signal dicts (for counter_thesis, strategy_confidence,
verdict) plus the pre-computed trade_setup for optional price levels —
kept here as a focused helper so `recommendation_builder.py` stays a thin
section orchestrator.
"""

from __future__ import annotations

from agents.retro.parser import SECTION_SKIP_THESE
from pipeline.recommendation_helpers import SIGNAL_CONFIDENCE, build_verdict
from shared.rules.skip_selector import SkipEntry


def build_skip_recs(
    skip_entries: list[SkipEntry],
    sector_signal_by_ticker: dict[str, dict],
    gated_by_ticker: dict[str, dict],
    beliefs_by_ticker: dict[str, dict],
    trade_setups_by_ticker: dict[str, dict],
) -> list[dict]:
    """Materialize SkipEntry list as rec rows with enrichment."""
    recs: list[dict] = []
    for entry in skip_entries:
        ticker = entry["ticker"]
        signal = sector_signal_by_ticker.get(ticker) or {}
        gated = gated_by_ticker.get(ticker) or {}
        setup = trade_setups_by_ticker.get(ticker, {})
        rec: dict = {
            "ticker": ticker,
            "action": "SKIP",
            "section": SECTION_SKIP_THESE,
            "source": entry["source"],
            "rationale": entry["reason"],
            "counter_thesis": signal.get("key_risk") or gated.get("gated_by"),
            "belief_conviction": (beliefs_by_ticker.get(ticker) or {}).get("conviction"),
            "strategy_confidence": SIGNAL_CONFIDENCE.get(
                (signal.get("confidence") or "").upper(), 0.5
            ),
            "verdict": build_verdict(SECTION_SKIP_THESE, "SKIP", signal or gated),
        }
        if setup.get("valid"):
            rec["entry_price"] = setup.get("entry")
            rec["stop_price"] = setup.get("stop")
            rec["target_price"] = setup.get("target")
            rec["risk_reward"] = setup.get("risk_reward")
        recs.append(rec)
    return recs
