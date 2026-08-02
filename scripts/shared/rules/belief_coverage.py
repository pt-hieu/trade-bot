"""Belief coverage contract shared by the pipeline and the review collector.

Defines the canonical set of sub-agent keys expected per ensemble, plus an
optional-aggregator set whose absence logs ERROR but does NOT raise. Both
the live persistence path (`pipeline.phase_postprocess`) and the offline
review collector (`collect_review_data`) import from here so the contract
lives in one place.

Pure Python, no async / DB / LLM — matches the "shared/rules/" convention.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence

from shared.watchlist import HOLDINGS_SECTOR_KEY

# Sub-agents — missing these is a sub-agent regression. Coverage floor below.
EXPECTED_SECTOR_AGENT_KEYS: frozenset[str] = frozenset(
    {"sector_technical", "sector_news", "sector_enrichment"}
)
EXPECTED_POSITION_AGENT_KEYS: frozenset[str] = frozenset(
    {"positions_technical", "positions_value", "positions_thesis"}
)

# Aggregator agent_key literals — single source so producer (collect_review_data)
# and consumer (aggregator_persistence_zero) agree without a stringly-typed
# coupling.
SECTOR_AGGREGATOR_KEY = "sector_aggregator"
POSITIONS_AGGREGATOR_KEY = "positions_aggregator"

# Aggregators — their degradation path (`derive_alerts_from_subreports`) may
# emit zero aggregator beliefs on provider hangs. Absence here is legitimate
# on bad-data days, BUT it must not go silent: ERROR log + per-run counter
# so the operator can grep and pipeline_health_summary alerts.
OPTIONAL_SECTOR_AGENT_KEYS: frozenset[str] = frozenset({"sector_aggregator"})
OPTIONAL_POSITION_AGENT_KEYS: frozenset[str] = frozenset({"positions_aggregator"})

# Pseudo-sector keys exist for fetch convenience but are never fanned out to
# sector sub-agents — held-but-unwatched tickers would otherwise count as
# expected and trip the coverage gate without any path to receive beliefs.
WATCHLIST_PSEUDO_SECTORS: frozenset[str] = frozenset({HOLDINGS_SECTOR_KEY})


def sector_coverage_universe(
    sectors_for_phase2: Mapping[str, Sequence[str]],
) -> frozenset[str]:
    """Build the per-ticker coverage-gate universe from Phase 2's sector dict.

    Pseudo-sector keys are dropped so the gate's "expected" set equals the
    tickers sub-agents actually run on, not the broader fetch universe.
    """
    return frozenset(
        ticker
        for sector_key, tickers in sectors_for_phase2.items()
        if sector_key not in WATCHLIST_PSEUDO_SECTORS
        for ticker in tickers
    )


def count_coverage_by_agent(beliefs: list[dict]) -> dict[str, int]:
    """Return `{agent_key: count}` for a beliefs list."""
    return dict(Counter(b.get("agent_key") or "?" for b in beliefs))


def missing_agent_keys(beliefs: list[dict], expected: frozenset[str]) -> list[str]:
    """Return sorted keys from `expected` that have no rows in `beliefs`."""
    observed = {b.get("agent_key") or "?" for b in beliefs}
    return sorted(expected - observed)


def _tickers_with_any_belief(beliefs: list[dict]) -> set[str]:
    """Return the set of tickers that have at least one belief row."""
    return {b.get("ticker") or "" for b in beliefs if b.get("ticker")}


# Empirical P5 of per-agent ticker coverage over 2026-04-13..2026-05-13 review
# bundles ≈ 0.85; the 2026-04-29 SWI-141 incident dipped to 0.69, one stddev
# below this floor. Choosing 0.85 keeps healthy days silent while surfacing
# next-tier degradations before they reach synthesis_picks.
DEFAULT_COVERAGE_RATIO_FLOOR = 0.85


def per_agent_ticker_coverage(
    beliefs: list[dict],
    expected_agents: frozenset[str],
    expected_tickers: frozenset[str],
) -> dict[str, list[str]]:
    """Return ``{agent_key: sorted(missing_tickers)}`` for each expected agent.

    Only agents with at least one missing ticker appear in the result, so
    the payload stays compact on healthy days. SWI-116 / SWI-126: review-time
    surfacing of which sub-agent dropped which tickers — previously the
    aggregator-level gate hid this granularity.
    """
    by_agent: dict[str, set[str]] = {agent: set(expected_tickers) for agent in expected_agents}
    for belief in beliefs:
        agent_key = belief.get("agent_key") or ""
        ticker = belief.get("ticker") or ""
        if agent_key in by_agent and ticker:
            by_agent[agent_key].discard(ticker)
    return {agent: sorted(missing) for agent, missing in by_agent.items() if missing}


def coverage_degraded_agents(
    per_agent_missing: dict[str, list[str]],
    expected_tickers: frozenset[str],
    ratio_floor: float = DEFAULT_COVERAGE_RATIO_FLOOR,
) -> list[str]:
    """Return agents whose per-ticker coverage fell below ``ratio_floor``."""
    total = len(expected_tickers) or 1
    return sorted(
        agent
        for agent, missing in per_agent_missing.items()
        if (total - len(missing)) / total < ratio_floor
    )


def aggregator_persistence_zero(
    beliefs: list[dict],
    aggregator_key: str,
    sectors_attempted: frozenset[str],
) -> list[str]:
    """Return sectors that fired ``sector_subagent_attempt`` but persisted zero aggregator beliefs.

    Distinct from the OPTIONAL_*_AGENT_KEYS gate, which forgives a fully
    skipped aggregator. This flags the "ran but emitted nothing" mode that
    SWI-116 surfaced on 2026-05-13 — visible only by cross-referencing the
    belief table with the attempt-span set. ``aggregator_key`` is typically
    ``"sector_aggregator"`` or ``"positions_aggregator"``.
    """
    sectors_with_beliefs = {
        belief.get("sector_key") or ""
        for belief in beliefs
        if belief.get("agent_key") == aggregator_key
    }
    return sorted(sectors_attempted - sectors_with_beliefs)


def assert_belief_coverage(
    beliefs: list[dict],
    expected_keys: frozenset[str],
    *,
    ensemble_label: str,
    logger: logging.Logger,
    optional_keys: frozenset[str] = frozenset(),
    expected_tickers: frozenset[str] | None = None,
) -> None:
    """Fail loud when sub-agent belief coverage is catastrophically short.

    Two levels of checks (SWI-141 / Fix 7a — per-ticker is the sufficient
    root, agent-key is the necessary belt-and-suspenders).

    Agent-key thresholds (``expected_keys``):
      0 missing — silent (happy path).
      1 missing — ERROR log only.
      2+ missing — ``RuntimeError``.

    Per-ticker thresholds (``expected_tickers``, optional):
      0 missing — silent.
      1 missing — ERROR log only.
      2+ missing — ``RuntimeError``. The 2026-04-29 incident shipped a
      24/35-coverage swing brief because the agent-key set was complete
      while 11 individual tickers had ZERO sub-agent beliefs. Per-ticker
      check catches that shape directly.

    Optional keys (aggregators):
      Any missing — ERROR log + observability counter bump; never raises.
    """
    if not beliefs:
        # SWI-191: zero beliefs of ANY kind is total coverage collapse — the
        # most expensive failure mode (a brief that ships with no ensemble
        # signal). Gate the raise on `expected_tickers` — the real "work was
        # expected" signal — NOT the agent-key set, which is an always-non-empty
        # constant. A no-holdings day legitimately yields zero position beliefs
        # (empty universe → empty expected_tickers); raising there would abort a
        # healthy pipeline, the exact over-conservative failure the
        # failure-mode-asymmetry rule disfavors. Collapse fires only when there
        # were tickers to analyze yet nothing came back.
        if expected_tickers:
            collapse_msg = (
                f"{ensemble_label.upper()}_TOTAL_COVERAGE_COLLAPSE "
                f"zero beliefs persisted; expected_keys={sorted(expected_keys)} "
                f"expected_ticker_count={len(expected_tickers)}"
            )
            logger.error(collapse_msg)
            raise RuntimeError(collapse_msg)
        return
    observed = count_coverage_by_agent(beliefs)

    missing_required = sorted(expected_keys - set(observed.keys()))
    if missing_required:
        msg = (
            f"{ensemble_label.upper()}_BELIEF_COVERAGE_GAP "
            f"missing={missing_required} observed={observed}"
        )
        logger.error(msg)
        if len(missing_required) >= 2:
            raise RuntimeError(msg)

    # SWI-233 owns the per-ticker threshold — do not touch 186–197 in Wave 1.
    # Known retained risk: this 2+-missing raise can still kill a tradeable
    # brief on a high-coverage day (contradicts the failure-mode-asymmetry
    # rule). Deliberately deferred to SWI-233 (Wave 2), not silently frozen.
    if expected_tickers:
        observed_tickers = _tickers_with_any_belief(beliefs)
        missing_tickers = sorted(expected_tickers - observed_tickers)
        if missing_tickers:
            ticker_msg = (
                f"{ensemble_label.upper()}_TICKER_COVERAGE_GAP "
                f"missing_tickers={missing_tickers} "
                f"observed_count={len(observed_tickers)}/{len(expected_tickers)}"
            )
            logger.error(ticker_msg)
            if len(missing_tickers) >= 2:
                raise RuntimeError(ticker_msg)

    missing_optional = sorted(optional_keys - set(observed.keys()))
    if missing_optional:
        logger.error(
            "%s_AGGREGATOR_BELIEF_GAP missing=%s observed=%s",
            ensemble_label.upper(),
            missing_optional,
            observed,
        )
        # Observability is advisory — narrow to ImportError so a
        # genuine bug in record_aggregator_belief_gap surfaces instead
        # of being swallowed under the ERROR log above.
        try:
            from shared.observability import record_aggregator_belief_gap
        except ImportError:
            return
        for key in missing_optional:
            record_aggregator_belief_gap(ensemble=ensemble_label, agent_key=key)
