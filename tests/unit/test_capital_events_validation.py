"""SWI-125 Surface 7: capital_events ticker validation at model + renderer.

May 12 brief shipped a catalyst-summary row reading ': ipo 2026 (du kien) (?)'
because `_persist_discoveries` accepted empty ticker verbatim and the
renderer didn't filter. Validator now rejects empty / whitespace / sentinel
('UNK', 'N/A', etc.) and shape-checks against the VN 3-5 char alnum
uppercase pattern; renderer applies the same filter defensively for legacy
rows.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.capital_events import CapitalEvent


def _kwargs(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "event_type": "ipo",
        "description": "x",
        "expected_date": "2026-06",
        "impact": "WATCH",
        "source": "test",
    }


def test_empty_ticker_rejected() -> None:
    with pytest.raises(ValidationError):
        CapitalEvent(**_kwargs(""))


def test_whitespace_only_ticker_rejected() -> None:
    with pytest.raises(ValidationError):
        CapitalEvent(**_kwargs("   "))


@pytest.mark.parametrize("sentinel", ["UNK", "unk", "Unk", "NONE", "null", "N/A", "-"])
def test_sentinel_ticker_rejected_case_insensitive(sentinel: str) -> None:
    with pytest.raises(ValidationError):
        CapitalEvent(**_kwargs(sentinel))


@pytest.mark.parametrize("bad", ["AB", "ABCDEF", "fpt"])  # lowercase, 2-char, 6-char
def test_invalid_shape_rejected(bad: str) -> None:
    # lowercase 'fpt' fails because re fullmatch is case-sensitive on the
    # uppercased input; the validator uppercases internally only after the
    # sentinel check, but the shape regex runs against the upper form.
    # 'fpt' passes shape after uppercase BUT 'AB' / 'ABCDEF' do not.
    # Re-check semantics: validator uppercases via `.strip().upper()` then
    # regex check — so lowercase becomes uppercase and passes; only length
    # extremes fail. Use only the length-failing cases here.
    if bad.upper().isalnum() and 3 <= len(bad) <= 5:
        pytest.skip("Shape-valid after uppercasing")
    with pytest.raises(ValidationError):
        CapitalEvent(**_kwargs(bad))


@pytest.mark.parametrize("good", ["SAB", "FPT", "VNM", "SBT11", "PVS"])
def test_valid_ticker_passes_and_uppercased(good: str) -> None:
    event = CapitalEvent(**_kwargs(good))
    assert event.ticker == good.upper()


def test_lowercase_ticker_uppercased() -> None:
    event = CapitalEvent(**_kwargs("fpt"))
    assert event.ticker == "FPT"
