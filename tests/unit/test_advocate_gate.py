"""Tests for advocate gate — deterministic pick filtering from advocate verdicts."""

from pipeline.phase_advocate import (
    BEAR_CHALLENGE_CONFIDENCE_THRESHOLD,
    MIN_SURVIVING_PICKS,
    _evaluate_gate_decision,
    apply_advocate_gate,
)


def _make_pick(ticker: str, risk_reward: float = 3.5, sector: str = "banking") -> dict:
    return {"ticker": ticker, "risk_reward": risk_reward, "sector": sector}


def _make_review(ticker: str, verdict: str, confidence: float = 0.5) -> dict:
    return {
        "ticker": ticker,
        "verdict": verdict,
        "confidence": confidence,
        "key_arguments": [f"Argument for {ticker}"],
        "blind_spots": [],
    }


class TestGateDecisionMatrix:
    """Each verdict combination produces the correct gate/warn/pass decision."""

    def test_bear_challenge_high_conf_bull_agree_gates_pick(self):
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "CHALLENGE", 0.85),
            bull_review=_make_review("FPT", "AGREE", 0.7),
        )
        assert decision["should_gate"] is True
        assert decision["reason"] == "bear_high_confidence_challenge"

    def test_both_challenge_gates_pick(self):
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "CHALLENGE", 0.5),
            bull_review=_make_review("FPT", "CHALLENGE", 0.6),
        )
        assert decision["should_gate"] is True
        assert decision["reason"] == "both_reviewers_challenge"

    def test_bear_challenge_low_conf_bull_agree_warns_only(self):
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "CHALLENGE", 0.5),
            bull_review=_make_review("FPT", "AGREE", 0.8),
        )
        assert decision["should_gate"] is False
        assert decision["warn"] is True
        assert decision["reason"] == "bear_low_confidence_challenge"

    def test_bear_challenge_bull_mixed_warns_only(self):
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "CHALLENGE", 0.8),
            bull_review=_make_review("FPT", "MIXED", 0.6),
        )
        assert decision["should_gate"] is False
        assert decision["warn"] is True
        assert decision["reason"] == "bear_challenge_bull_mixed"

    def test_bear_agree_bull_agree_passes(self):
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "AGREE", 0.8),
            bull_review=_make_review("FPT", "AGREE", 0.9),
        )
        assert decision["should_gate"] is False
        assert decision["warn"] is False

    def test_bear_mixed_passes(self):
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "MIXED", 0.7),
            bull_review=_make_review("FPT", "AGREE", 0.8),
        )
        assert decision["should_gate"] is False
        assert decision["warn"] is False

    def test_no_reviews_passes(self):
        decision = _evaluate_gate_decision(bear_review=None, bull_review=None)
        assert decision["should_gate"] is False
        assert decision["warn"] is False

    def test_bear_challenge_at_threshold_does_not_gate(self):
        """Confidence exactly at threshold should NOT gate (> not >=)."""
        decision = _evaluate_gate_decision(
            bear_review=_make_review("FPT", "CHALLENGE", BEAR_CHALLENGE_CONFIDENCE_THRESHOLD),
            bull_review=_make_review("FPT", "AGREE", 0.8),
        )
        assert decision["should_gate"] is False
        assert decision["warn"] is True


class TestApplyAdvocateGate:
    """Integration tests for the full gate pipeline."""

    def test_empty_reviews_bypasses_gate_and_warns(self):
        picks = [_make_pick("FPT"), _make_pick("VCB")]
        filtered, gated = apply_advocate_gate(picks, {"bull": [], "bear": []})
        assert len(filtered) == 2
        assert len(gated) == 0

    def test_enforce_mode_removes_gated_picks(self, monkeypatch):
        monkeypatch.setenv("ADVOCATE_GATE_MODE", "enforce")
        picks = [_make_pick("FPT", 4.0), _make_pick("VCB", 3.5)]
        reviews = {
            "bull": [_make_review("FPT", "AGREE", 0.7), _make_review("VCB", "AGREE", 0.8)],
            "bear": [_make_review("FPT", "CHALLENGE", 0.85), _make_review("VCB", "AGREE", 0.7)],
        }
        filtered, gated = apply_advocate_gate(picks, reviews)
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "VCB"
        assert len(gated) == 1
        assert gated[0]["ticker"] == "FPT"

    def test_audit_mode_logs_but_keeps_all_picks(self, monkeypatch):
        monkeypatch.setenv("ADVOCATE_GATE_MODE", "audit")
        picks = [_make_pick("FPT", 4.0)]
        reviews = {
            "bull": [_make_review("FPT", "AGREE", 0.7)],
            "bear": [_make_review("FPT", "CHALLENGE", 0.85)],
        }
        filtered, gated = apply_advocate_gate(picks, reviews)
        # Audit mode: all picks survive
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "FPT"
        # But gated_tickers still populated for SKIP THESE context
        assert len(gated) == 1

    def test_min_surviving_picks_rescues_best_pick(self, monkeypatch):
        monkeypatch.setenv("ADVOCATE_GATE_MODE", "enforce")
        picks = [_make_pick("FPT", 4.5), _make_pick("VCB", 3.0)]
        reviews = {
            "bull": [_make_review("FPT", "CHALLENGE", 0.6), _make_review("VCB", "CHALLENGE", 0.5)],
            "bear": [_make_review("FPT", "CHALLENGE", 0.8), _make_review("VCB", "CHALLENGE", 0.7)],
        }
        filtered, gated = apply_advocate_gate(picks, reviews)
        # Both would be gated (both_reviewers_challenge), but best R:R rescued
        assert len(filtered) >= MIN_SURVIVING_PICKS
        assert filtered[0]["ticker"] == "FPT"  # Best R:R
        assert filtered[0].get("advocate_warning") is True

    def test_reallocation_safety_protects_exit_pair(self, monkeypatch):
        monkeypatch.setenv("ADVOCATE_GATE_MODE", "enforce")
        picks = [_make_pick("FPT", 4.0)]
        reviews = {
            "bull": [_make_review("FPT", "AGREE", 0.7)],
            "bear": [_make_review("FPT", "CHALLENGE", 0.85)],
        }
        position_alerts = {"alerts": [{"ticker": "FPT", "action": "EXIT"}]}
        filtered, gated = apply_advocate_gate(
            picks, reviews, position_alerts=position_alerts, trading_mode="REALLOCATION"
        )
        # FPT protected because it has a matching EXIT in REALLOCATION mode
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "FPT"
        assert filtered[0].get("advocate_warning") is True
        assert len(gated) == 0

    def test_returns_new_list_not_in_place_mutation(self, monkeypatch):
        monkeypatch.setenv("ADVOCATE_GATE_MODE", "enforce")
        original_picks = [_make_pick("FPT", 4.0), _make_pick("VCB", 3.5)]
        reviews = {
            "bull": [_make_review("FPT", "AGREE"), _make_review("VCB", "AGREE")],
            "bear": [_make_review("FPT", "CHALLENGE", 0.85), _make_review("VCB", "AGREE")],
        }
        filtered, _ = apply_advocate_gate(original_picks, reviews)
        # Original list must be unchanged
        assert len(original_picks) == 2

    def test_gated_tickers_include_bear_arguments(self, monkeypatch):
        monkeypatch.setenv("ADVOCATE_GATE_MODE", "enforce")
        picks = [_make_pick("FPT")]
        bear_review = _make_review("FPT", "CHALLENGE", 0.85)
        bear_review["key_arguments"] = ["Overvalued at P/E 25x", "Insider selling"]
        reviews = {
            "bull": [_make_review("FPT", "AGREE")],
            "bear": [bear_review],
        }
        _, gated = apply_advocate_gate(picks, reviews)
        # min_surviving rescues it, but let's check gated has arguments
        # Actually with only 1 pick and rescue logic, gated will be empty
        # Use 2 picks to test this properly
        picks = [_make_pick("FPT"), _make_pick("VCB", 5.0)]
        reviews["bull"].append(_make_review("VCB", "AGREE"))
        reviews["bear"].append(_make_review("VCB", "AGREE"))
        _, gated = apply_advocate_gate(picks, reviews)
        assert len(gated) == 1
        assert gated[0]["ticker"] == "FPT"
        assert "Overvalued at P/E 25x" in gated[0]["bear_arguments"]
