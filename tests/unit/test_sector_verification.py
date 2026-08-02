"""Unit tests for sector.py guardrails and signal verification."""

from agents.sector import (
    TickerSignal,
    _apply_cash_gate,
    _apply_coverage_gaps,
    _apply_regime_downgrade,
)

# ── Coverage Gaps ────────────────────────────────────────────────────────────


class TestCoverageGaps:
    def test_no_gaps(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test")]
        result = _apply_coverage_gaps(signals, ["FPT"])
        assert len(result) == 1

    def test_missing_ticker_with_no_subagent_views_silently_dropped(self):
        """SWI-141 / Fix 7b: tickers with zero sub-agent coverage no longer
        get a fabricated [COVERAGE_GAP] WAIT placeholder. The per-ticker
        coverage gate (Fix 7a) raises when 2+ such tickers occur; a single
        gap ERROR-logs and ships without the placeholder."""
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test")]
        result = _apply_coverage_gaps(signals, ["FPT", "TCB"], sub_reports=[])
        assert len(result) == 1
        assert result[0].ticker == "FPT"

    def test_case_insensitive(self):
        signals = [TickerSignal(ticker="fpt", signal="BUY", note="test")]
        result = _apply_coverage_gaps(signals, ["FPT"])
        assert len(result) == 1


# ── Regime Downgrade ─────────────────────────────────────────────────────────


class TestRegimeDowngrade:
    def test_no_downgrade_in_calm(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test", confidence="MEDIUM")]
        result = _apply_regime_downgrade(signals, "CALM")
        assert result[0].signal == "BUY"

    def test_risk_off_does_not_downgrade(self):
        # Anti-conservatism fix (2026-02-28): downgrade only fires in CRISIS,
        # never in RISK_OFF. RISK_OFF BUYs now pass through to the entry gates
        # where higher-level circuit breakers apply instead.
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test", confidence="MEDIUM")]
        result = _apply_regime_downgrade(signals, "RISK_OFF")
        assert result[0].signal == "BUY"
        assert "[REGIME_DOWNGRADE]" not in result[0].note

    def test_high_confidence_survives_crisis(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test", confidence="HIGH")]
        result = _apply_regime_downgrade(signals, "CRISIS")
        assert result[0].signal == "BUY"

    def test_downgrade_medium_in_crisis(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test", confidence="MEDIUM")]
        result = _apply_regime_downgrade(signals, "CRISIS")
        assert result[0].signal == "WATCH"
        assert "[REGIME_DOWNGRADE]" in result[0].note

    def test_downgrade_low_in_crisis(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test", confidence="LOW")]
        result = _apply_regime_downgrade(signals, "CRISIS")
        assert result[0].signal == "WATCH"


# ── Cash Gate ────────────────────────────────────────────────────────────────


class TestCashGate:
    def test_no_gate_when_entries_allowed(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test")]
        result = _apply_cash_gate(signals, entries_allowed=True)
        assert result[0].signal == "BUY"

    def test_buy_to_watch_when_blocked(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="test")]
        result = _apply_cash_gate(signals, entries_allowed=False)
        assert result[0].signal == "WATCH"
        assert "[CASH_GATE]" in result[0].note

    def test_watch_unaffected(self):
        signals = [TickerSignal(ticker="FPT", signal="WATCH", note="test")]
        result = _apply_cash_gate(signals, entries_allowed=False)
        assert result[0].signal == "WATCH"
        assert "[CASH_GATE]" not in result[0].note


# ── Per-ticker BUY verification logic ────────────────────────────────────────


class TestBuyVerificationLogic:
    """Test the verification logic directly by simulating what analyze_sector_with_agent does."""

    def _run_verification(
        self, signals: list[TickerSignal], ticker_tools: dict[str, set[str]]
    ) -> list[TickerSignal]:
        """Replicate the verification loop from analyze_sector_with_agent."""
        verified = []
        for s in signals:
            if s.signal == "BUY":
                tools_used = ticker_tools.get(s.ticker.upper(), set())
                has_technicals = "tool_get_technicals" in tools_used
                has_valuation = "tool_get_valuation_history" in tools_used
                if not has_technicals:
                    s = s.model_copy(update={"signal": "WATCH", "note": f"[UNVERIFIED] {s.note}"})
                elif not has_valuation:
                    s = s.model_copy(update={"note": f"[NO_VALUATION] {s.note}"})
            verified.append(s)
        return verified

    def test_buy_with_both_tools_unchanged(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="RSI 35")]
        tools = {"FPT": {"tool_get_technicals", "tool_get_valuation_history"}}
        result = self._run_verification(signals, tools)
        assert result[0].signal == "BUY"
        assert "[UNVERIFIED]" not in result[0].note
        assert "[NO_VALUATION]" not in result[0].note

    def test_buy_without_technicals_downgraded_to_watch(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="Strong momentum")]
        tools = {"FPT": {"tool_get_valuation_history"}}  # no technicals
        result = self._run_verification(signals, tools)
        assert result[0].signal == "WATCH"
        assert result[0].note.startswith("[UNVERIFIED]")

    def test_buy_without_valuation_gets_flag(self):
        signals = [TickerSignal(ticker="FPT", signal="BUY", note="RSI 35 at support")]
        tools = {"FPT": {"tool_get_technicals"}}  # no valuation
        result = self._run_verification(signals, tools)
        assert result[0].signal == "BUY"  # not downgraded
        assert result[0].note.startswith("[NO_VALUATION]")

    def test_buy_with_no_tools_at_all_downgraded(self):
        signals = [TickerSignal(ticker="VHM", signal="BUY", note="Breakout")]
        tools = {}  # agent called no tools for this ticker
        result = self._run_verification(signals, tools)
        assert result[0].signal == "WATCH"
        assert result[0].note.startswith("[UNVERIFIED]")

    def test_watch_signal_not_affected(self):
        signals = [TickerSignal(ticker="TCB", signal="WATCH", note="Consolidating")]
        tools = {}
        result = self._run_verification(signals, tools)
        assert result[0].signal == "WATCH"
        assert "[UNVERIFIED]" not in result[0].note

    def test_avoid_signal_not_affected(self):
        signals = [TickerSignal(ticker="HPG", signal="AVOID", note="Downtrend")]
        tools = {}
        result = self._run_verification(signals, tools)
        assert result[0].signal == "AVOID"

    def test_mixed_signals_only_buy_checked(self):
        signals = [
            TickerSignal(ticker="FPT", signal="BUY", note="RSI 35"),
            TickerSignal(ticker="TCB", signal="WATCH", note="Resistance"),
            TickerSignal(ticker="HPG", signal="AVOID", note="Downtrend"),
            TickerSignal(ticker="VHM", signal="BUY", note="Breakout"),
        ]
        # FPT has both tools, VHM has no tools
        tools = {
            "FPT": {"tool_get_technicals", "tool_get_valuation_history"},
        }
        result = self._run_verification(signals, tools)

        fpt = next(s for s in result if s.ticker == "FPT")
        tcb = next(s for s in result if s.ticker == "TCB")
        hpg = next(s for s in result if s.ticker == "HPG")
        vhm = next(s for s in result if s.ticker == "VHM")

        assert fpt.signal == "BUY"
        assert tcb.signal == "WATCH"
        assert hpg.signal == "AVOID"
        assert vhm.signal == "WATCH"
        assert vhm.note.startswith("[UNVERIFIED]")

    def test_ticker_case_insensitive_matching(self):
        """Signal ticker 'fpt' should match tools key 'FPT'."""
        signals = [TickerSignal(ticker="fpt", signal="BUY", note="Test")]
        tools = {"FPT": {"tool_get_technicals", "tool_get_valuation_history"}}
        result = self._run_verification(signals, tools)
        assert result[0].signal == "BUY"
        assert "[UNVERIFIED]" not in result[0].note

    def test_original_note_preserved_in_unverified_prefix(self):
        original_note = "Hammer candle at 200MA"
        signals = [TickerSignal(ticker="VIC", signal="BUY", note=original_note)]
        tools = {}
        result = self._run_verification(signals, tools)
        assert original_note in result[0].note

    def test_original_note_preserved_in_no_valuation_prefix(self):
        original_note = "RSI 32 oversold"
        signals = [TickerSignal(ticker="VIC", signal="BUY", note=original_note)]
        tools = {"VIC": {"tool_get_technicals"}}
        result = self._run_verification(signals, tools)
        assert original_note in result[0].note
