"""Tests for merge_split_sector_results — failure-preserving merge.

Regression guard for 2026-04-20 Phase 2 collapse: when every chunk of a
split sector errored, the merge returned a success-shaped dict with
empty `signals`, so `failed_sector_count` never incremented and the
health gate passed. Now it must return the first Exception instead.
"""

from pipeline.sector_utils import merge_split_sector_results


def test_all_chunks_exception_returns_exception():
    split_map = {"banking_1": ["TCB"], "banking_2": ["VCB"]}
    err1 = TypeError("'>=' not supported between instances of 'dict' and 'int'")
    err2 = ValueError("whatever")
    results = {"sector_banking_1": err1, "sector_banking_2": err2}

    merged = merge_split_sector_results(results, {"banking": ["TCB", "VCB"]}, split_map)

    # First encountered Exception is surfaced — phase_parallel health gate
    # relies on `isinstance(value, Exception)` to count the failure.
    assert isinstance(merged["banking"], Exception)
    assert merged["banking"] is err1


def test_mixed_success_and_exception_preserves_survivor_signals():
    split_map = {"banking_1": ["TCB"], "banking_2": ["VCB"]}
    err = TypeError("boom")
    success = {
        "text": "## banking_2\nOK",
        "signals": [{"ticker": "VCB", "signal": "BUY"}],
        "beliefs": [{"ticker": "VCB", "conviction": "high"}],
    }
    results = {"sector_banking_1": err, "sector_banking_2": success}

    merged = merge_split_sector_results(results, {"banking": ["TCB", "VCB"]}, split_map)

    assert isinstance(merged["banking"], dict)
    assert merged["banking"]["signals"] == [{"ticker": "VCB", "signal": "BUY"}]
    assert merged["banking"]["beliefs"] == [{"ticker": "VCB", "conviction": "high"}]
    # Failure stub is in the text for synthesis readability, but signals
    # contain only the survivor.
    assert "banking_1" in merged["banking"]["text"]
    assert "Analysis failed: boom" in merged["banking"]["text"]
    assert "## banking_2" in merged["banking"]["text"]


def test_no_chunks_at_all_returns_none():
    split_map = {"banking_1": ["TCB"]}
    # Results missing the key entirely
    merged = merge_split_sector_results({}, {"banking": ["TCB"]}, split_map)
    assert merged["banking"] is None


def test_unsplit_sector_passthrough_unchanged():
    """Sectors absent from split_sectors_map flow through as-is."""
    split_map = {"technology": ["FPT"]}  # technology is the sector key itself
    results = {"sector_technology": {"text": "ok", "signals": [], "beliefs": []}}

    merged = merge_split_sector_results(results, {"technology": ["FPT"]}, split_map)

    assert merged["technology"] == {"text": "ok", "signals": [], "beliefs": []}
