"""Tests for _calc_consensus — consensus label aligned with final action."""

from unittest.mock import MagicMock

from agents.positions_ensemble_rules import _calc_consensus


def _make_report(views: list[tuple[str, str]]):
    """Create a mock AnalystReport with views [(ticker, action), ...]."""
    report = MagicMock()
    mock_views = []
    for ticker, action in views:
        view = MagicMock()
        view.ticker = ticker
        view.action = action
        mock_views.append(view)
    report.views = mock_views
    return report


class TestCalcConsensus:
    """Consensus label reflects alignment with the final action."""

    def test_unanimous_all_agree_with_final(self):
        technical = _make_report([("FPT", "HOLD")])
        value = _make_report([("FPT", "HOLD")])
        thesis = _make_report([("FPT", "HOLD")])
        assert _calc_consensus("FPT", "HOLD", technical, value, thesis) == "unanimous"

    def test_majority_two_agree_with_final(self):
        technical = _make_report([("FPT", "ADD")])
        value = _make_report([("FPT", "ADD")])
        thesis = _make_report([("FPT", "HOLD")])
        assert _calc_consensus("FPT", "ADD", technical, value, thesis) == "majority"

    def test_minority_override_one_agrees_with_final(self):
        technical = _make_report([("FPT", "HOLD")])
        value = _make_report([("FPT", "ADD")])
        thesis = _make_report([("FPT", "HOLD")])
        assert _calc_consensus("FPT", "ADD", technical, value, thesis) == "minority_override"

    def test_full_override_none_agree_with_final(self):
        technical = _make_report([("FPT", "HOLD")])
        value = _make_report([("FPT", "TRIM")])
        thesis = _make_report([("FPT", "HOLD")])
        assert _calc_consensus("FPT", "EXIT", technical, value, thesis) == "override"

    def test_no_data_no_views_for_ticker(self):
        technical = _make_report([("TCB", "HOLD")])
        value = _make_report([("TCB", "HOLD")])
        thesis = _make_report([("TCB", "HOLD")])
        assert _calc_consensus("FPT", "ADD", technical, value, thesis) == "no_data"

    def test_case_insensitive_ticker(self):
        technical = _make_report([("fpt", "HOLD")])
        value = _make_report([("FPT", "HOLD")])
        thesis = _make_report([("Fpt", "HOLD")])
        assert _calc_consensus("FPT", "HOLD", technical, value, thesis) == "unanimous"

    def test_case_insensitive_action(self):
        technical = _make_report([("FPT", "add")])
        value = _make_report([("FPT", "Add")])
        thesis = _make_report([("FPT", "ADD")])
        assert _calc_consensus("FPT", "add", technical, value, thesis) == "unanimous"

    def test_partial_views_two_of_three_agree(self):
        """When only 2 agents have views and both agree with final."""
        technical = _make_report([("FPT", "HOLD")])
        value = _make_report([("FPT", "HOLD")])
        thesis = _make_report([])  # no view for FPT
        assert _calc_consensus("FPT", "HOLD", technical, value, thesis) == "unanimous"
