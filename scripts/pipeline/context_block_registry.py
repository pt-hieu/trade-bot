"""Registry mapping context-block format functions to the output keys they emit.

The pre-commit injection-coherence hook reads this registry to validate YAML
``injected_fields:`` claims structurally. Without a registry the hook can only
do lexical matching on prompt prose, which is brittle: it both false-positives
on free-text mentions of tool names and false-negatives on the case that
crashed the 2026-04-28 morning scan (a YAML claiming a thesis was injected
when no formatter ever rendered it).

Each entry names the format function (canonical Python identifier) and the
``output_keys`` it produces. Keys are dot-paths (``thesis.pillars``,
``valuation.history``, …) so a future reviewer can read a YAML and walk the
registry to confirm every claim has a concrete renderer.

When you add a new ``format_*`` block, add a single entry to
``FORMATTER_DEFINITIONS``. When you rename a formatter, update its name in
that one record — the ``injected_fields:`` lists in YAML stay valid because
they reference *output keys*, not function names.
"""

from __future__ import annotations

from typing import TypedDict


class FormatterEntry(TypedDict):
    """One registered context-block formatter and the keys it injects."""

    function: str
    output_keys: list[str]
    description: str


# Single source of truth — one record per formatter. ``OUTPUT_KEY_REGISTRY``
# is derived below by exploding each record's ``output_keys`` into a flat
# `key → entry` lookup.
FORMATTER_DEFINITIONS: list[FormatterEntry] = [
    {
        "function": "format_portfolio_block",
        "output_keys": ["portfolio.holdings", "portfolio.cash"],
        "description": "Holdings + cash + deployable lines",
    },
    {
        "function": "format_regime_block",
        "output_keys": ["regime.market_level", "regime.macro_signals", "regime.valuation"],
        "description": "VN-Index regime + global macro + market valuation",
    },
    {
        "function": "format_ticker_briefings",
        "output_keys": [
            "ticker.technicals",
            "ticker.flow",
            "ticker.insider",
            "ticker.relative_strength",
            "ticker.beliefs",
            "ticker.company_profile",
            "ticker.commodity_transmission",
            "ticker.macro_signal_transmission",
            "ticker.geopolitical_label",
            "ticker.longterm_summary",
            "ticker.narrative",
            "ticker.articles",
            "ticker.catalyst",
            "ticker.trade_setup",
        ],
        "description": "Per-ticker compact briefing (technicals, flow, insider, RS, beliefs, profile, commodity/macro transmission, geo label, longterm, narrative, articles, catalyst, trade setup)",
    },
    {
        "function": "format_calibration_block",
        "output_keys": ["calibration.accuracy"],
        "description": "Belief accuracy prose (Brier, win rate, calibration)",
    },
    {
        "function": "format_thesis_pillars_block",
        "output_keys": ["thesis.pillars", "thesis.kill_criteria", "thesis.last_update"],
        "description": "Thesis tracker pillars + active kill criteria + last update",
    },
    {
        "function": "format_valuation_block",
        "output_keys": ["valuation.current", "valuation.earnings_quality", "valuation.history"],
        "description": "Current PE/PB/ROE + earnings quality + 8Q history per held ticker",
    },
    {
        "function": "format_trades_block",
        "output_keys": ["trades.recent"],
        "description": "Recent trades prose",
    },
    {
        "function": "format_learnings_block",
        "output_keys": ["learnings.cache"],
        "description": "Pre-fetched learnings (summary, calibration, sector_bias, …)",
    },
    {
        "function": "format_memory_block",
        "output_keys": ["memory.patterns"],
        "description": "Similar days + winning/losing patterns + trading rules",
    },
    {
        "function": "format_rotation_block",
        "output_keys": ["rotation.sectors"],
        "description": "Sector rotation hot/cold prose",
    },
    {
        "function": "format_sector_data_block",
        "output_keys": ["sector.data"],
        "description": "Sector RSI/price data prose",
    },
    {
        "function": "format_executed_trades_block",
        "output_keys": ["executed_trades.today"],
        "description": "Today's executed trades prose",
    },
    {
        "function": "format_midday_prices_block",
        "output_keys": ["midday.prices"],
        "description": "Midday OHLCV per ticker",
    },
    {
        "function": "format_commodity_block",
        "output_keys": ["commodity.prices"],
        "description": "Global commodity prices block",
    },
    {
        "function": "format_vn_economy_block",
        "output_keys": ["vn_economy"],
        "description": "Vietnam macro economy snapshot",
    },
    {
        "function": "format_articles_block",
        "output_keys": ["articles.summary"],
        "description": "Article summaries (headlines + 1-line summaries)",
    },
    {
        "function": "format_company_profile_block",
        "output_keys": ["company_profiles"],
        "description": "Company profile (sector, business, moat, sensitivities)",
    },
]


# Derived flat lookup: each output key → its owning entry. Built once at
# import; the coherence hook calls ``known_output_keys()`` to validate
# YAML claims against this set.
OUTPUT_KEY_REGISTRY: dict[str, FormatterEntry] = {
    key: entry for entry in FORMATTER_DEFINITIONS for key in entry["output_keys"]
}


def known_output_keys() -> set[str]:
    """Return the set of every registered output key (used by the coherence hook)."""
    return set(OUTPUT_KEY_REGISTRY.keys())
