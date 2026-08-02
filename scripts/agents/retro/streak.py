"""Deterministic 0-BUY streak detector.

Per CLAUDE.md "Deterministic calculations only in Python" — streak
length, start date, and gate-profile classification are computed here
from ``daily_records`` rows; the retro and morning-brief LLM agents
only *describe* the streak object this module produces.

Inputs are the raw `daily_records` rows already loaded by `learnings`;
no DB access in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GateProfile = Literal["regime_gated", "belief_flattening", "rr_floor", "mixed"]


@dataclass(frozen=True)
class StreakAlert:
    """Detected 0-BUY streak summary.

    Attributes:
        length: number of consecutive 0-BUY trading days inside the window.
        start_date: ISO date of the first 0-BUY day in the streak.
        gate_profile: classification — which gate is most likely behind it.
            * regime_gated — most days had market_regime CAUTIOUS/CRISIS
            * belief_flattening — buy_signal_count > 0 but buy_rec_count = 0
            * rr_floor — gates triggered post-signal, not regime-driven
            * mixed — multiple causes
    """

    length: int
    start_date: str
    gate_profile: GateProfile

    def to_jsonb(self) -> dict[str, object]:
        return {
            "length": self.length,
            "start_date": self.start_date,
            "gate_profile": self.gate_profile,
        }


# Trigger threshold: 3+ of last 5 trading days with buy_rec_count == 0.
_TRIGGER_LOOKBACK_DAYS = 5
_MIN_STREAK_LENGTH = 3
_REGIME_GATED_REGIMES = frozenset({"CAUTIOUS", "CRISIS"})

# Length-measurement window — decoupled from the trigger window so the
# reported `length` reflects the TRUE contiguous zero-BUY suffix rather
# than the 5-day trigger slice. Must satisfy
# `_LENGTH_LOOKBACK_DAYS >= _STREAK_STRUCTURAL_LENGTH` from
# `recommendation_gate.py`; an inter-module contract test pins this.
_LENGTH_LOOKBACK_DAYS = 30


def assert_streak_fetch_nonempty(
    streak_rows: list,
    *,
    scan_date: object,
    fetch_failed: bool,
    table_has_rows: bool = True,
) -> None:
    """Fail loud when a SUCCESSFUL daily_records fetch returned zero rows (SWI-374).

    ``detect_zero_buy_streak`` returns ``None`` for BOTH an empty
    ``daily_records`` fetch AND a genuine no-streak — indistinguishable. A
    zero-row fetch for a ``scan_date`` that should have a record is a
    daily_records gap, not a clean "no streak", and must not masquerade as
    SUCCESS. Three states are distinguished:
      * fetch *exception* (``fetch_failed=True``) → non-fatal (caller logged it).
      * empty fetch but ``table_has_rows=False`` (genuinely empty table:
        bootstrap / reseed / backfill window) → non-fatal no-op; raising would
        abort the whole retro on a legitimate empty-table day.
      * empty fetch while the table HAS rows elsewhere → a real gap for this
        ``scan_date`` → raise.
    """
    if not fetch_failed and len(streak_rows) == 0 and table_has_rows:
        raise RuntimeError(f"streak fetch returned 0 rows for {scan_date} — daily_records gap")


def detect_zero_buy_streak(
    daily_records: list[dict],
    *,
    has_high_positive_macro_catalyst: bool = False,
) -> StreakAlert | None:
    """Return a StreakAlert when a 0-BUY streak ≥3 in last 5 days, else None.

    `daily_records` MUST be ordered ascending by ``record_date`` and contain
    the most recent N days at the tail. Each row must expose
    ``record_date``, ``buy_rec_count``, ``buy_signal_count``, ``market_regime``.

    ``has_high_positive_macro_catalyst`` reshapes the surface profile when
    the 0-BUY streak co-occurs with an active HIGH-confidence POSITIVE
    macro-blanket catalyst (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002).
    Instead of returning the usual ``belief_flattening`` /
    ``regime_gated`` label — both of which the existing relax branch
    ignores — the classifier returns ``rr_floor`` so the ratcheted
    3/7/10-day relax staircase fires. This routes the relief through
    the existing profile gate rather than introducing a new branch.

    Snapshot semantics (SWI-125 Surface 3 doc fix, baseline ``b7a75f5a``
    introduced in SWI-93):

    * Retro of Day N writes ``daily_records.streak_alert_json`` for the
      row whose ``record_date = N`` at EOD.
    * Morning gate of Day N+1 reads that blob via
      ``pipeline/helpers/derive.py::get_streak_alert(scan_date - 1)`` and
      embeds it into ``daily_records.gate_decision_json.inputs_digest.streak_alert``
      on the Day N+1 row at scan time.
    * Retro of Day N+1 then overwrites the Day N+1 row's
      ``streak_alert_json`` at EOD.

    The two columns on the same Day N+1 row therefore reflect *different
    write times against different windows by design*: the gate-decision
    snapshot is "what the morning saw" (T-1 retro output); the
    streak_alert_json on the same row is "what retro recomputed after
    market close" (T-0 retro output). Cross-column ``length`` or
    ``start_date`` divergence is the expected signature — only
    ``gate_profile`` divergence is a regression signal.
    """
    if not daily_records:
        return None

    # Trigger condition reads the recent 5-day window. Profile classification
    # also reads this window — recent-pattern signal, not 30-day cumulative.
    trigger_window = daily_records[-_TRIGGER_LOOKBACK_DAYS:]
    zero_buy_in_trigger = [row for row in trigger_window if (row.get("buy_rec_count") or 0) == 0]
    if len(zero_buy_in_trigger) < _MIN_STREAK_LENGTH:
        return None

    # Length measurement reads a wider window so a multi-week streak
    # finally surfaces as `length=20+` instead of being capped at the
    # trigger-window size (SWI-3b.1).
    length_window = daily_records[-_LENGTH_LOOKBACK_DAYS:]
    contiguous = 0
    for row in reversed(length_window):
        if (row.get("buy_rec_count") or 0) == 0:
            contiguous += 1
        else:
            break
    if contiguous < _MIN_STREAK_LENGTH:
        # Streak detected by trigger but suffix is broken; floor to the
        # trigger-window zero-BUY count so the alert still surfaces.
        contiguous = len(zero_buy_in_trigger)

    # Start date is anchored on the contiguous suffix when possible so the
    # reported window matches the reported length; falls back to the
    # earliest zero-BUY in the trigger window otherwise.
    streak_rows = length_window[-contiguous:] if contiguous <= len(length_window) else length_window
    start_date = str(
        (streak_rows[0] if streak_rows else zero_buy_in_trigger[0]).get("record_date") or ""
    )

    profile = _classify_gate_profile(
        zero_buy_in_trigger,
        has_high_positive_macro_catalyst=has_high_positive_macro_catalyst,
    )
    return StreakAlert(length=contiguous, start_date=start_date, gate_profile=profile)


def _classify_gate_profile(
    zero_buy_rows: list[dict],
    *,
    has_high_positive_macro_catalyst: bool = False,
) -> GateProfile:
    """Decide which gate(s) most plausibly produced the streak."""
    regime_count = sum(
        1
        for row in zero_buy_rows
        if (row.get("market_regime") or "").upper() in _REGIME_GATED_REGIMES
    )
    flat_count = sum(
        1
        for row in zero_buy_rows
        if (row.get("buy_signal_count") or 0) > 0 and (row.get("buy_rec_count") or 0) == 0
    )
    n = len(zero_buy_rows)
    regime_majority = regime_count >= max(1, n // 2 + 1)
    flat_majority = flat_count >= max(1, n // 2 + 1)

    if regime_majority and not flat_majority:
        profile: GateProfile = "regime_gated"
    elif flat_majority and not regime_majority:
        profile = "belief_flattening"
    elif not regime_majority and not flat_majority and flat_count > 0:
        profile = "rr_floor"
    elif regime_majority and flat_majority:
        profile = "mixed"
    else:
        profile = "rr_floor"

    # Macro-relief override: an active HIGH POSITIVE macro-blanket catalyst
    # is the exact tailwind that makes belief_flattening / regime_gated
    # days actually tradeable. Flip the surface profile to ``rr_floor``
    # so the existing streak relax branch (recommendation_gate.py) fires
    # instead of leaving the streak untreated.
    if has_high_positive_macro_catalyst and profile in ("belief_flattening", "regime_gated"):
        return "rr_floor"
    return profile
