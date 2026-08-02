#!/usr/bin/env python3
"""Unit tests for watchlist post-hoc validators."""

from scripts.agents.watchlist_update import StockScore
from scripts.agents.watchlist_validators import (
    detect_churn,
    enforce_sector_cap,
    filter_existing_additions,
    flag_overbought_stocks,
    remove_portfolio_conflicts,
    validate_confidence,
)


def _stock(
    ticker: str, sector: str = "Banking", score: int = 60, confidence: str = "medium"
) -> StockScore:
    """Helper to create a StockScore with minimal boilerplate."""
    return StockScore(
        ticker=ticker,
        sector=sector,
        score=score,
        confidence=confidence,
        reasons=[f"Test reason (+{score})"],
    )


# ── enforce_sector_cap ───────────────────────────────────────────────────────


class TestEnforceSectorCap:
    def test_trims_excess_keeps_top_two(self):
        additions = [
            _stock("BCM", "Real Estate", 70),
            _stock("KBC", "Real Estate", 55),
            _stock("IDC", "Real Estate", 60),
        ]
        result = enforce_sector_cap(additions, max_per_sector=2)
        tickers = {stock.ticker for stock in result}
        assert tickers == {"BCM", "IDC"}
        assert len(result) == 2

    def test_no_change_under_limit(self):
        additions = [
            _stock("STB", "Banking", 65),
            _stock("BCM", "Real Estate", 55),
            _stock("ACB", "Banking", 50),
        ]
        result = enforce_sector_cap(additions, max_per_sector=2)
        assert len(result) == 3

    def test_multiple_sectors_capped_independently(self):
        additions = [
            _stock("A", "Banking", 70),
            _stock("B", "Banking", 60),
            _stock("C", "Banking", 50),
            _stock("D", "Real Estate", 80),
            _stock("E", "Real Estate", 40),
        ]
        result = enforce_sector_cap(additions, max_per_sector=2)
        tickers = {stock.ticker for stock in result}
        assert tickers == {"A", "B", "D", "E"}

    def test_empty_list(self):
        assert enforce_sector_cap([]) == []

    def test_single_addition(self):
        result = enforce_sector_cap([_stock("STB")])
        assert len(result) == 1


# ── remove_portfolio_conflicts ───────────────────────────────────────────────


class TestRemovePortfolioConflicts:
    def test_adds_auto_removal_for_held_ticker(self):
        removals = [_stock("HPG", "Infrastructure", 50)]
        result = remove_portfolio_conflicts(
            current_watchlist={"TCB", "HPG", "ACB"},
            held_tickers={"TCB"},
            removals=removals,
        )
        assert len(result) == 2
        auto_removed = [r for r in result if r.ticker == "TCB"]
        assert len(auto_removed) == 1
        assert auto_removed[0].score == 100
        assert "[AUTO]" in auto_removed[0].reasons[0]

    def test_no_overlap_no_change(self):
        removals = [_stock("HPG", "Infrastructure", 50)]
        result = remove_portfolio_conflicts(
            current_watchlist={"ACB", "HPG"},
            held_tickers={"FPT"},
            removals=removals,
        )
        assert len(result) == 1

    def test_already_in_removals_no_duplicate(self):
        removals = [_stock("TCB", "Banking", 50)]
        result = remove_portfolio_conflicts(
            current_watchlist={"TCB", "ACB"},
            held_tickers={"TCB"},
            removals=removals,
        )
        # TCB already in removals, should not be doubled
        assert len(result) == 1

    def test_multiple_conflicts(self):
        result = remove_portfolio_conflicts(
            current_watchlist={"TCB", "FPT", "ACB"},
            held_tickers={"TCB", "FPT"},
            removals=[],
        )
        tickers = {r.ticker for r in result}
        assert tickers == {"TCB", "FPT"}


# ── validate_confidence ──────────────────────────────────────────────────────


class TestValidateConfidence:
    """Fixtures intentionally use the NESTED technicals shape.

    `validate_confidence` is fed by `watchlist_ensemble.py` which imports
    `fetch_technicals_batch` directly from `shared.vnstock_client` (raw
    client path) — NOT `shared.api.technicals.get_technicals` (which
    flattens). Do NOT flip these fixtures to flat; they correctly model
    the raw-client producer. See Fix 1 in the 2026-04-20 Phase 2 collapse
    plan for why the two shapes coexist.
    """

    def test_downgrade_on_bearish_supertrend(self):
        additions = [_stock("STB", confidence="high")]
        technicals = {"STB": {"supertrend": {"direction": "DOWN"}}}
        result = validate_confidence(additions, technicals)
        assert result[0].confidence == "medium"

    def test_no_downgrade_when_not_high(self):
        additions = [_stock("STB", confidence="medium")]
        technicals = {"STB": {"supertrend": {"direction": "DOWN"}}}
        result = validate_confidence(additions, technicals)
        assert result[0].confidence == "medium"

    def test_low_on_multiple_conflicts(self):
        additions = [_stock("STB", confidence="high")]
        technicals = {
            "STB": {
                "supertrend": {"direction": "DOWN"},
                "adx": {"adx": 15},
            }
        }
        result = validate_confidence(additions, technicals)
        assert result[0].confidence == "low"

    def test_no_downgrade_clean_technicals(self):
        additions = [_stock("STB", confidence="high")]
        technicals = {
            "STB": {
                "supertrend": {"direction": "UP"},
                "adx": {"adx": 30},
                "close": 50000,
                "sma50": 48000,
            }
        }
        result = validate_confidence(additions, technicals)
        assert result[0].confidence == "high"


# ── detect_churn ─────────────────────────────────────────────────────────────


class TestDetectChurn:
    def test_no_previous_report(self):
        additions = [_stock("STB")]
        removals = [_stock("HPG")]
        result_additions, result_removals = detect_churn(additions, removals, None)
        assert len(result_additions) == 1
        assert len(result_removals) == 1

    def test_churn_penalty_applied(self):
        additions = [_stock("HPG", score=60)]
        removals = []
        previous_report = {"additions": [], "removals": [{"ticker": "HPG"}]}
        result_additions, _ = detect_churn(additions, removals, previous_report)
        assert result_additions[0].score < 60
        assert any("[CHURN]" in reason for reason in result_additions[0].reasons)


# ── filter_existing_additions ─────────────────────────────────────────────────


class TestFilterExistingAdditions:
    def test_removes_duplicate(self):
        additions = [_stock("GAS", "State-Owned"), _stock("NLG", "Real Estate")]
        result = filter_existing_additions(additions, current_watchlist={"GAS", "ACB"})
        assert len(result) == 1
        assert result[0].ticker == "NLG"

    def test_no_duplicates_passes_all(self):
        additions = [_stock("NLG"), _stock("HPG")]
        result = filter_existing_additions(additions, current_watchlist={"GAS", "ACB"})
        assert len(result) == 2

    def test_all_duplicates_returns_empty(self):
        additions = [_stock("GAS"), _stock("ACB")]
        result = filter_existing_additions(additions, current_watchlist={"GAS", "ACB"})
        assert len(result) == 0

    def test_empty_additions(self):
        result = filter_existing_additions([], current_watchlist={"GAS"})
        assert result == []

    def test_empty_watchlist(self):
        additions = [_stock("GAS")]
        result = filter_existing_additions(additions, current_watchlist=set())
        assert len(result) == 1


# ── flag_overbought_stocks ────────────────────────────────────────────────────


class TestFlagOverboughtStocks:
    def test_overbought_non_pinned_proposes_removal(self):
        additions = []
        removals = []
        technicals = {"VHM": {"rsi": 75.0}, "ACB": {"rsi": 45.0}}
        result_additions, result_removals = flag_overbought_stocks(
            additions,
            removals,
            current_watchlist={"VHM", "ACB"},
            pinned_tickers=set(),
            technicals=technicals,
        )
        assert len(result_removals) == 1
        assert result_removals[0].ticker == "VHM"
        assert result_removals[0].score == 40
        assert "[POST-HOC]" in result_removals[0].reasons[0]

    def test_overbought_pinned_no_removal(self):
        additions = []
        removals = []
        technicals = {"VHM": {"rsi": 75.0}}
        result_additions, result_removals = flag_overbought_stocks(
            additions,
            removals,
            current_watchlist={"VHM"},
            pinned_tickers={"VHM"},
            technicals=technicals,
        )
        assert len(result_removals) == 0

    def test_warning_zone_annotates_addition(self):
        additions = [_stock("DXS", "Infrastructure")]
        technicals = {"DXS": {"rsi": 63.73}}
        result_additions, _ = flag_overbought_stocks(
            additions, [], current_watchlist=set(), pinned_tickers=set(), technicals=technicals
        )
        assert any("[WARNING]" in reason for reason in result_additions[0].reasons)

    def test_normal_rsi_no_annotation(self):
        additions = [_stock("ACB")]
        technicals = {"ACB": {"rsi": 45.0}}
        result_additions, _ = flag_overbought_stocks(
            additions, [], current_watchlist=set(), pinned_tickers=set(), technicals=technicals
        )
        assert not any("[WARNING]" in reason for reason in result_additions[0].reasons)

    def test_missing_rsi_no_crash(self):
        additions = [_stock("ACB")]
        technicals = {"ACB": {}}
        result_additions, result_removals = flag_overbought_stocks(
            additions, [], current_watchlist={"ACB"}, pinned_tickers=set(), technicals=technicals
        )
        assert len(result_additions) == 1
        assert len(result_removals) == 0

    def test_already_in_removals_no_duplicate(self):
        removals = [_stock("VHM", "Real Estate", 50)]
        technicals = {"VHM": {"rsi": 75.0}}
        _, result_removals = flag_overbought_stocks(
            [], removals, current_watchlist={"VHM"}, pinned_tickers=set(), technicals=technicals
        )
        # VHM already in removals — should not be doubled
        assert len(result_removals) == 1
