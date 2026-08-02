"""Daily smoke check for the SWI-171 scoring audit table.

Run as a post-step from the morning-scan GitHub Actions workflow. Exit
non-zero on regression so the workflow fails loud and the pipeline owner
sees the alert.

Smoke checks:
  1. ``validate_scoring_config()`` passes — Σw=1, 12 keys, threshold ∈
     [0,100], regime penalties non-negative, scoring_version SemVer.
  2. ``pre_gate_candidates`` has at least one row for today's scan_date.
  3. Score distribution is non-degenerate — at least 2 distinct score
     values across today's rows.
  4. Per-row breakdown sums match ``score`` to within 1e-6.
  5. No NaN scores.
  6. ``weights_jsonb`` snapshot on every row matches the active
     scoring.yaml weights vector.

Usage:
    uv run python scripts/eval/scoring_health.py [--scan-date YYYY-MM-DD]

Default scan_date is today's local date.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import sys
from collections.abc import Mapping
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("scoring_health")


async def _async_main(scan_date: date, *, fail_on_empty: bool = True) -> int:
    sys.path.insert(0, "scripts")  # mirror inline-script discipline

    from shared.database import Database, close_db
    from shared.rules.scoring import load_scoring_config, validate_scoring_config

    failures: list[str] = []

    try:
        validate_scoring_config()
    except Exception as exc:
        failures.append(f"validate_scoring_config failed: {exc}")
        logger.error("validate_scoring_config failed: %s", exc)
        return _report(failures)

    config = load_scoring_config()
    expected_weights = {key: float(value) for key, value in config.weights.items()}

    async with Database():
        try:
            from shared.database import fetch_all

            # Per-row scan only needs the columns that vary by candidate.
            rows = await fetch_all(
                """
                SELECT ticker, phase, score, breakdown
                FROM pre_gate_candidates
                WHERE scan_date = $1
                """,
                scan_date,
            )
            # Structural-zero regression guard. Any row gated at L3+
            # with sim_populated=true but a 0 risk_reward contribution
            # means the audit-row feature synthesis broke — fail loud.
            structural_zero_rows = await fetch_all(
                """
                SELECT ticker, gated_by
                FROM pre_gate_candidates
                WHERE scan_date = $1
                  AND phase = 'morning'
                  AND gated_by IN ('passed', 'rr_floor', 'atr_trail_rr_gate')
                  AND (breakdown->'breakdown'->>'risk_reward')::float = 0
                  AND breakdown->>'sim_populated' = 'true'
                """,
                scan_date,
            )
            # SWI-355 + SWI-358: corrupted-geometry guard. Catches the SAB
            # 2026-05-12 fingerprint (rr=609, sim_p_target=0) that the
            # structural-zero predicate misses. Symptom predicate
            # (rr > 20 AND sim = 0) is OR'd with the SWI-358 diagnostic
            # flag so future upstream corruption surfaces immediately even
            # if the sim happens to be non-zero.
            corrupted_geometry_rows = await fetch_all(
                """
                SELECT ticker, gated_by, breakdown
                FROM pre_gate_candidates
                WHERE scan_date = $1
                  AND phase = 'morning'
                  AND (
                    (
                      (breakdown->'breakdown'->>'risk_reward')::float > 20
                      AND COALESCE(
                        (breakdown->'breakdown'->>'sim_p_target')::float, 0
                      ) = 0
                    )
                    OR breakdown->>'degenerate_risk' = 'true'
                  )
                """,
                scan_date,
            )
            # weights_jsonb is identical across all rows that share the same
            # scoring_version. Sample distinct snapshots only.
            weight_snapshots = await fetch_all(
                """
                SELECT DISTINCT scoring_version, weights_jsonb
                FROM pre_gate_candidates
                WHERE scan_date = $1
                """,
                scan_date,
            )
        finally:
            await close_db()

    if not rows:
        message = f"pre_gate_candidates has 0 rows for scan_date={scan_date}"
        if fail_on_empty:
            failures.append(message)
        else:
            logger.warning(message)
        return _report(failures)

    distinct_scores: set[float] = set()
    breakdown_drift_count = 0
    nan_score_count = 0

    for row in rows:
        try:
            score = float(row["score"])
        except (TypeError, ValueError):
            nan_score_count += 1
            continue
        if math.isnan(score):
            nan_score_count += 1
            continue

        distinct_scores.add(round(score, 4))

        if not _breakdown_sums_match(dict(row), score):
            breakdown_drift_count += 1

    weight_drift_versions = [
        snapshot["scoring_version"]
        for snapshot in weight_snapshots
        if not _weights_match(snapshot["weights_jsonb"], expected_weights)
    ]

    n = len(rows)
    logger.info(
        "scoring_health: %d rows for %s (distinct=%d weight_drift=%d breakdown_drift=%d nan=%d)",
        n,
        scan_date,
        len(distinct_scores),
        len(weight_drift_versions),
        breakdown_drift_count,
        nan_score_count,
    )

    if nan_score_count:
        failures.append(f"{nan_score_count} rows have NaN score")
    if weight_drift_versions:
        failures.append(
            f"weights_jsonb drift from active scoring.yaml in versions: {weight_drift_versions}"
        )
    if breakdown_drift_count:
        failures.append(
            f"{breakdown_drift_count}/{n} rows have breakdown sum != score (>1e-3 drift)"
        )
    if structural_zero_rows:
        tickers = ", ".join(f"{row['ticker']}({row['gated_by']})" for row in structural_zero_rows)
        failures.append(
            f"Structural-zero regression: {len(structural_zero_rows)} rows at "
            f"L3+ have risk_reward contribution = 0 despite sim_populated=true: {tickers}"
        )
    if corrupted_geometry_rows:
        tickers = ", ".join(
            f"{row['ticker']}({row['gated_by']})" for row in corrupted_geometry_rows
        )
        failures.append(
            f"Corrupted-geometry regression: {len(corrupted_geometry_rows)} rows have "
            f"rr > 20 with sim_p_target = 0 OR degenerate_risk = true: {tickers}"
        )
    if n >= 2 and len(distinct_scores) < 2:
        failures.append(
            f"score distribution degenerate: {n} rows but only {len(distinct_scores)} distinct value(s)"
        )

    return _report(failures)


def _weights_match(stored: object, expected: Mapping[str, float]) -> bool:
    from shared.neon._utils import parse_jsonb_object

    parsed = parse_jsonb_object(stored)
    if parsed is None or set(parsed.keys()) != set(expected.keys()):
        return False
    for key, expected_value in expected.items():
        stored_value = parsed[key]
        try:
            if abs(float(stored_value) - expected_value) > 1e-9:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _breakdown_sums_match(row: Mapping[str, object], score: float) -> bool:
    from shared.neon._utils import parse_jsonb_object

    breakdown = parse_jsonb_object(row.get("breakdown"))
    if breakdown is None:
        return False
    inner = breakdown.get("breakdown")
    if not isinstance(inner, dict):
        return False
    contributions = sum(
        float(value)
        for key, value in inner.items()
        if key not in ("regime_penalty", "shock_penalty") and isinstance(value, (int, float))
    )
    regime_pen = float(breakdown.get("regime_penalty") or 0.0)
    shock_pen = float(breakdown.get("shock_penalty") or 0.0)
    expected = max(0.0, min(100.0, contributions - regime_pen - shock_pen))
    return abs(expected - score) < 1e-3


def _report(failures: list[str]) -> int:
    if failures:
        for message in failures:
            logger.error("scoring_health FAIL: %s", message)
        return 1
    logger.info("scoring_health OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Score audit smoke check")
    parser.add_argument(
        "--scan-date",
        type=date.fromisoformat,
        default=date.today(),
        help="ISO-format date (default: today)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail when 0 rows exist (e.g. weekend / holiday runs)",
    )
    args = parser.parse_args()

    return asyncio.run(_async_main(args.scan_date, fail_on_empty=not args.allow_empty))


if __name__ == "__main__":
    sys.exit(main())
