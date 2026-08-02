"""Tests for sector.py degradation path (T04).

When the sector_aggregator LLM times out OR the primary model is unhealthy
(T03's ProviderUnavailable), sector.py must derive signals from the three
sub-agent views rather than emit [AGGREGATOR_TIMEOUT] placeholders.
"""

from agents.belief_models import TickerBelief
from agents.sector import _derive_signals_from_subreports, _wait_fallback
from agents.sector_analysts import SectorAnalystReport, SectorAnalystView


def _belief(ticker: str, direction: str = "NEUTRAL") -> TickerBelief:
    return TickerBelief(
        ticker=ticker,
        belief_narrative="test narrative",
        direction=direction,  # type: ignore[arg-type]
        bull_probability=0.33,
        base_probability=0.34,
        bear_probability=0.33,
        price_target_vnd=100000,
        conviction=0.5,
        belief_status="NEW",
    )


def _view(ticker: str, signal: str, confidence: int, reasoning: str) -> SectorAnalystView:
    return SectorAnalystView(
        ticker=ticker,
        signal=signal,  # type: ignore[arg-type]
        confidence=confidence,
        reasoning=reasoning,
        belief=_belief(ticker),
    )


class TestDeriveSignalsFromSubreports:
    def test_majority_bullish_produces_buy_signal(self):
        technical = SectorAnalystReport(
            views=[_view("FPT", "BUY", 8, "Momentum breakout above 200DMA.")],
            summary="Technicals bullish",
        )
        news = SectorAnalystReport(
            views=[_view("FPT", "BUY", 7, "AI services contract signed.")],
            summary="News bullish",
        )
        enrichment = SectorAnalystReport(
            views=[_view("FPT", "WAIT", 5, "Flow neutral.")],
            summary="Enrichment mixed",
        )

        result = _derive_signals_from_subreports(
            technical=technical,
            news=news,
            enrichment=enrichment,
            tickers=["FPT"],
            sector_name="Technology",
            degradation_type="TimeoutError",
        )

        assert len(result.signals) == 1
        fpt_signal = result.signals[0]
        assert fpt_signal.ticker == "FPT"
        assert fpt_signal.signal == "BUY"
        assert "[DERIVED_FROM_BELIEFS]" in fpt_signal.note
        # Note should carry the highest-confidence matching view's excerpt.
        assert "Momentum" in fpt_signal.note or "AI services" in fpt_signal.note

    def test_mixed_views_do_not_collapse_to_all_wait(self):
        # Different tickers get different direction-aware signals.
        technical = SectorAnalystReport(
            views=[
                _view("TCB", "BUY", 7, "Breakout setup."),
                _view("VHM", "AVOID", 6, "Regulatory overhang."),
            ],
            summary="Mixed technicals",
        )
        news = SectorAnalystReport(
            views=[
                _view("TCB", "BUY", 6, "Credit growth upgrade."),
                _view("VHM", "AVOID", 7, "Property credit concerns."),
            ],
            summary="Mixed news",
        )
        enrichment = SectorAnalystReport(
            views=[
                _view("TCB", "WATCH", 5, "Flow neutral."),
                _view("VHM", "WATCH", 5, "Insider flat."),
            ],
            summary="Neutral enrichment",
        )

        result = _derive_signals_from_subreports(
            technical=technical,
            news=news,
            enrichment=enrichment,
            tickers=["TCB", "VHM"],
            sector_name="Banking",
            degradation_type="TimeoutError",
        )

        signals_by_ticker = {s.ticker: s for s in result.signals}
        assert signals_by_ticker["TCB"].signal == "BUY"
        assert signals_by_ticker["VHM"].signal == "AVOID"
        for signal in result.signals:
            assert "[DERIVED_FROM_BELIEFS]" in signal.note

    def test_missing_ticker_views_fall_through_to_wait(self):
        # No sub-agent produced a view for MBB — helper must still emit a
        # row (not skip the ticker) and label it WAIT.
        technical = SectorAnalystReport(views=[], summary="Empty")
        news = SectorAnalystReport(views=[], summary="Empty")
        enrichment = SectorAnalystReport(views=[], summary="Empty")

        result = _derive_signals_from_subreports(
            technical=technical,
            news=news,
            enrichment=enrichment,
            tickers=["MBB"],
            sector_name="Banking",
            degradation_type="ProviderUnavailable",
        )

        assert len(result.signals) == 1
        assert result.signals[0].signal == "WAIT"
        assert "[DERIVED_FROM_BELIEFS]" in result.signals[0].note
        assert "ProviderUnavailable" in result.summary

    def test_bullish_tiebreak_picks_buy_over_wait(self):
        # 1 BUY, 1 WATCH, 1 WAIT — all different. Tiebreak rule picks
        # bullish-leaning (BUY > WATCH > WAIT > AVOID).
        technical = SectorAnalystReport(
            views=[_view("HPG", "BUY", 8, "Inventory clearing.")], summary="Bull"
        )
        news = SectorAnalystReport(
            views=[_view("HPG", "WATCH", 6, "Steel demand tepid.")], summary="Mixed"
        )
        enrichment = SectorAnalystReport(
            views=[_view("HPG", "WAIT", 5, "Flow flat.")], summary="Neutral"
        )

        result = _derive_signals_from_subreports(
            technical=technical,
            news=news,
            enrichment=enrichment,
            tickers=["HPG"],
            sector_name="Materials",
            degradation_type="TimeoutError",
        )

        assert result.signals[0].signal == "BUY"


# ── Bug 10 (run2 2026-05-14): degradation paths must synthesize beliefs ───
# When the aggregator hangs, _derive_signals_from_subreports previously
# returned beliefs=[] → no sector_aggregator belief rows → belief_coverage
# gap (43/48). _wait_fallback (all-3-failed path) had the same gap. Both
# now synthesize AggregatedBelief rows.


class TestDegradationPathsSynthesizeBeliefs:
    def test_derive_signals_synthesizes_one_belief_per_ticker(self):
        """Aggregator hung, 2-3 sub-agents alive → one AggregatedBelief per
        ticker with a valid direction and price_target_vnd >= 1."""
        technical = SectorAnalystReport(views=[_view("TCB", "BUY", 8, "Breakout.")], summary="Bull")
        news = SectorAnalystReport(
            views=[_view("TCB", "BUY", 7, "Credit upgrade.")], summary="Bull"
        )
        enrichment = SectorAnalystReport(
            views=[_view("TCB", "WATCH", 5, "Flow neutral.")], summary="Mixed"
        )

        result = _derive_signals_from_subreports(
            technical=technical,
            news=news,
            enrichment=enrichment,
            tickers=["TCB"],
            sector_name="Banking",
            degradation_type="TimeoutError",
        )

        assert len(result.beliefs) == 1
        belief = result.beliefs[0]
        assert belief.ticker == "TCB"
        assert belief.direction in ("BULLISH", "BEARISH", "NEUTRAL")
        assert belief.price_target_vnd >= 1
        assert "[DERIVED_FROM_BELIEFS]" in belief.belief_narrative

    def test_derive_signals_skips_ticker_with_no_views(self, caplog):
        """A ticker with zero landed sub-agent views has no price source —
        its belief is skipped + logged, never built as an invalid model."""
        technical = SectorAnalystReport(views=[_view("TCB", "BUY", 8, "Breakout.")], summary="Bull")
        news = SectorAnalystReport(views=[], summary="Empty")
        enrichment = SectorAnalystReport(views=[], summary="Empty")

        with caplog.at_level("WARNING"):
            result = _derive_signals_from_subreports(
                technical=technical,
                news=news,
                enrichment=enrichment,
                tickers=["TCB", "MBB"],
                sector_name="Banking",
                degradation_type="TimeoutError",
            )

        belief_tickers = {b.ticker for b in result.beliefs}
        assert belief_tickers == {"TCB"}  # MBB skipped
        assert "MBB" in caplog.text
        # Signals still cover every ticker.
        assert {s.ticker for s in result.signals} == {"TCB", "MBB"}

    def test_wait_fallback_synthesizes_neutral_beliefs(self):
        """All-3-sub-agents-failed path → one NEUTRAL AggregatedBelief per
        ticker, priced from last_known_prices."""
        result = _wait_fallback(
            ["FPT", "TCB"],
            "[ALL_ANALYSTS_FAILED]",
            "All 3 analysts failed for Banking.",
            last_known_prices={"FPT": 97900, "TCB": 24300},
        )

        assert {b.ticker for b in result.beliefs} == {"FPT", "TCB"}
        for belief in result.beliefs:
            assert belief.direction == "NEUTRAL"
            assert belief.price_target_vnd >= 1
            assert "[DERIVED_FROM_BELIEFS]" in belief.belief_narrative

    def test_wait_fallback_skips_ticker_with_no_price(self, caplog):
        """A ticker absent from last_known_prices is skipped + logged."""
        with caplog.at_level("WARNING"):
            result = _wait_fallback(
                ["FPT", "TCB"],
                "[ALL_ANALYSTS_FAILED]",
                "All 3 analysts failed.",
                last_known_prices={"FPT": 97900},
            )

        assert {b.ticker for b in result.beliefs} == {"FPT"}
        assert "TCB" in caplog.text
        # WAIT signals still cover every ticker.
        assert {s.ticker for s in result.signals} == {"FPT", "TCB"}
