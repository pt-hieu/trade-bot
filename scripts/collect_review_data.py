#!/usr/bin/env python3
"""Pre-fetch pipeline review data to JSON files for skill consumption.

Usage:
    SWINGY_ENV=production uv run python scripts/collect_review_data.py --date 2026-04-02
    SWINGY_ENV=production uv run python scripts/collect_review_data.py --date 2026-04-02 --scope morning
"""

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict

EnvelopeKind = Literal["dict", "list", "prose"]


class ToolErrorEnvelope(TypedDict):
    tool: str
    span_id: str | None
    parent_span_id: str
    parent_agent: str
    kind: EnvelopeKind
    response: str


sys.path.insert(0, str(Path(__file__).parent))

from shared.env import load_env
from shared.market_calendar import is_trading_day
from shared.rules.belief_coverage import (
    EXPECTED_POSITION_AGENT_KEYS,
    EXPECTED_SECTOR_AGENT_KEYS,
    SECTOR_AGGREGATOR_KEY,
    aggregator_persistence_zero,
    count_coverage_by_agent,
    coverage_degraded_agents,
    missing_agent_keys,
    per_agent_ticker_coverage,
)

logger = logging.getLogger(__name__)

VIETNAM_TZ = timezone(timedelta(hours=7))

SCOPE_TO_WORKFLOWS = {
    "full": [
        "daily-scan.yml",
        "midday-check.yml",
        "market-close-retro.yml",
        "alert-analysis.yml",
        "catalyst-check.yml",
        "weekly-enrichment.yml",
        "weekly-watchlist-update.yml",
        "monthly-longterm-review.yml",
    ],
    "morning": ["daily-scan.yml"],
    "midday": ["midday-check.yml"],
    "retro": ["market-close-retro.yml"],
    "weekly": ["weekly-enrichment.yml", "weekly-watchlist-update.yml"],
    "alerts": ["alert-analysis.yml", "catalyst-check.yml"],
    "monthly": ["monthly-longterm-review.yml"],
}

CRITICAL_QUERIES = {"daily_record", "recommendations"}

# Expected Logfire root span names per scope, with VN schedule times.
# Used to warn when traces are absent (collector ran before pipeline fired).
# `trading_day_only=True` suppresses the warning on weekends/VN market holidays
# (the workflow's own market-calendar gate skips those steps by design).
SCOPE_EXPECTED_TRACES: dict[str, list[tuple[str, str, bool]]] = {
    "full": [
        ("morning_brief_generation", "07:00", True),
        ("news_pipeline_v2", "07:00", False),  # runs daily incl. weekends
        ("retrospective_generation", "15:00", True),
    ],
    "morning": [
        ("morning_brief_generation", "07:00", True),
        ("news_pipeline_v2", "07:00", False),
    ],
    "midday": [("midday_check", "12:30", True)],
    "retro": [("retrospective_generation", "15:00", True)],
    "weekly": [
        ("weekly_enrichment", "08:30", False),
        ("weekly_watchlist_update", "08:30", False),
    ],
}


def vietnam_day_utc_window(target_date: str) -> tuple[str, str]:
    """Convert a Vietnam calendar date to UTC boundary timestamps.

    Vietnam (ICT) is UTC+7, so:
      start: target_date 00:00 ICT = previous day 17:00 UTC
      end:   next_date 00:00 ICT = target_date 17:00 UTC
    """
    target = date.fromisoformat(target_date)
    yesterday = (target - timedelta(days=1)).isoformat()
    return f"{yesterday}T17:00:00Z", f"{target_date}T17:00:00Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect pipeline review data")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d"),
        help="Target date YYYY-MM-DD (default: today Vietnam TZ)",
    )
    parser.add_argument(
        "--scope",
        choices=["full", "morning", "midday", "retro", "weekly", "alerts", "monthly"],
        default="full",
        help="Pipeline scope (default: full)",
    )
    parser.add_argument(
        "--sync",
        dest="sync",
        action="store_true",
        default=True,
        help="git fetch + ff-merge before reading research/* (SWI-134, default)",
    )
    parser.add_argument(
        "--no-sync",
        dest="sync",
        action="store_false",
        help="skip the git sync (for tests / offline runs)",
    )
    return parser.parse_args()


def _sync_research_to_remote(repo_root: str) -> None:
    """SWI-134: ff-merge origin/main so research/* matches the producer's push.

    Logs and continues on any failure (dirty tree, network down, non-ff)
    rather than raising — operators can rebase manually if needed.
    """
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            timeout=30,
        )
        result = subprocess.run(
            ["git", "merge", "--ff-only", "origin/main"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            head_short = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            logger.warning(
                "research/* sync skipped: ff-merge failed (HEAD=%s, stderr=%s)",
                head_short,
                result.stderr.decode("utf-8", errors="replace").strip(),
            )
        else:
            print("  Synced research/* with origin/main (ff-only)")
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
        logger.warning("research/* sync skipped: %s", exc)


def validate_environment() -> None:
    """Refuse to run without production Neon URL."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "neon.tech" not in database_url:
        print(
            "FATAL: DATABASE_URL does not point to Neon. Set SWINGY_ENV=production before running.",
            file=sys.stderr,
        )
        sys.exit(1)


def json_serial(obj: Any) -> str | float:
    """JSON serializer for types not handled by default."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__float__"):
        return float(obj)
    if hasattr(obj, "hex"):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


# Fields to always strip from DB records (bloat, not useful for review)
STRIP_FIELDS = {"context_embedding"}


def strip_nulls(record: dict) -> dict:
    """Remove null-valued fields and known bloat fields from a record."""
    return {k: v for k, v in record.items() if v is not None and k not in STRIP_FIELDS}


def clean_data(data: Any) -> Any:
    """Strip nulls and embeddings from DB data before writing."""
    if isinstance(data, list):
        return [strip_nulls(item) if isinstance(item, dict) else item for item in data]
    if isinstance(data, dict):
        return strip_nulls(data)
    return data


def write_json(output_dir: Path, filename: str, data: Any, raw: bool = False) -> int:
    """Write data as JSON, return row count.

    Args:
        raw: If True, skip cleaning (for Logfire data that needs full attributes).
    """
    filepath = output_dir / filename
    cleaned = data if raw else clean_data(data)
    filepath.write_text(json.dumps(cleaned, default=json_serial, indent=2))
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        # Error payloads count as 0 rows so manifest "empty" detection actually fires.
        if "error" in data:
            return 0
        # Registry-shaped dicts (dict-of-tickers) report their length so
        # manifest reflects ticker count instead of a flat "1".
        if data and all(isinstance(v, dict) for v in data.values()):
            return len(data)
        return 1 if data else 0
    return 1 if data else 0


class MonitoringManifestEntry(TypedDict):
    status: str
    scaffolded: bool
    open_items: int
    escalated_items: int
    resolved_items: int
    served_stale_cache: bool


def copy_monitoring_items(output_dir: Path) -> MonitoringManifestEntry:
    """Export Linear regression-watch items into the review bundle.

    Pulls OPEN+ESCALATED and Done≤90d from Linear team Swingy via
    ``scripts/export_issues.py::run_export``; writes both
    ``monitoring_items.md`` and ``resolved_items.md`` into ``output_dir``.
    Fails open on Linear outage by serving the 7-day stale cache at
    ``scripts/linear_migration/last_export.md`` with a banner.
    """
    from export_issues import run_export

    try:
        result = run_export(output_dir)
    except Exception as exc:  # noqa: BLE001 — surface as warning, not a collector abort
        logger.warning("Linear export failed without stale cache fallback: %s", exc)
        return {
            "status": "error",
            "scaffolded": False,
            "open_items": 0,
            "escalated_items": 0,
            "resolved_items": 0,
            "served_stale_cache": False,
        }
    if result.served_stale_cache:
        logger.warning("Linear export served stale cache: %s", result.stale_cache_reason)
    return {
        "status": "ok",
        "scaffolded": False,
        "open_items": result.open_items,
        "escalated_items": result.escalated_items,
        "resolved_items": result.resolved_items,
        "served_stale_cache": result.served_stale_cache,
    }


async def _fetch_portfolio_plan_check(target_date: date) -> dict[str, Any]:
    """Per-(ticker, plan_type) grid + dual-listed detection for pipeline review.

    Delegates the DB read to `shared.rules.max_loss.fetch_portfolio_slices`
    so the review bundle stays in sync with the runtime rule module. Each
    slice is enriched with `days_since_entry` (trading-day count since
    earliest OPEN-lot entry, via the T+2 settlement snapshot) and
    `in_watchlist` (True iff ticker appears in SWING or LONGTERM watchlist)
    so pipeline-review subagents can gate T+2 and off-universe findings
    deterministically — see `.claude/skills/pipeline-review/instructions.md`
    gotchas.
    """
    from shared.neon.watchlist import load_all_watchlist_tickers
    from shared.rules.max_loss import fetch_portfolio_slices
    from shared.rules.settlement import load_open_trades_snapshot, trading_days_between

    rows, snapshot, watchlist_tickers = await asyncio.gather(
        fetch_portfolio_slices(),
        load_open_trades_snapshot(target_date),
        load_all_watchlist_tickers(),
    )

    per_plan: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        ticker = row.get("ticker") or ""
        plan_type = row.get("plan_type") or "UNKNOWN"
        entry_date = snapshot.earliest_entry_by_ticker.get(ticker)
        days_since_entry = trading_days_between(entry_date, target_date) if entry_date else None
        per_plan.setdefault(ticker, {})[plan_type] = {
            "shares": row.get("shares"),
            "avg_cost_vnd": row.get("avg_cost_vnd"),
            "current_price_vnd": row.get("current_price_vnd"),
            "holding_type": row.get("holding_type"),
            "days_since_entry": days_since_entry,
            "in_watchlist": ticker in watchlist_tickers,
        }
    dual_listed = sorted(t for t, plans in per_plan.items() if len(plans) > 1)
    return {
        "dual_listed_tickers": dual_listed,
        "per_plan": per_plan,
        "row_count": len(rows),
    }


async def _fetch_watchlist_membership() -> dict[str, Any]:
    """SWING vs LONGTERM watchlist ground truth for plan-type coherence audits."""
    from shared.neon.watchlist import get_longterm_watchlist, get_swing_watchlist

    swing_by_sector = await get_swing_watchlist()
    longterm_entries = await get_longterm_watchlist()
    swing = sorted({ticker for tickers in swing_by_sector.values() for ticker in tickers})
    longterm = sorted(longterm_entries.keys())
    return {
        "swing_watchlist": swing,
        "longterm_watchlist": longterm,
        "in_both": sorted(set(swing) & set(longterm)),
    }


async def _load_agent_configs_from_yaml_async() -> list[dict[str, object]]:
    """Load agent configs from YAML files for review data collection."""
    from shared.agent_config import CONFIGS_DIR, load_agent_config

    results: list[dict[str, object]] = []
    for config_file in sorted(CONFIGS_DIR.glob("*.yaml")):
        config = await load_agent_config(config_file.stem)
        results.append(
            {
                "agent_key": config.agent_key,
                "model_id": config.model_id,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
            }
        )
    return results


async def fetch_all_db_data(
    target_date: date,
) -> dict[str, Any]:
    """Run all DB queries concurrently. Returns {name: data_or_exception}."""
    from shared.database import close_db, fetch_one, fetch_val
    from shared.neon.belief_queries import get_all_belief_accuracy, get_unresolved_beliefs
    from shared.neon.insert_records import get_morning_recommendations
    from shared.neon.market import get_midday_check
    from shared.neon.portfolio import get_cash_balance, get_portfolio_holdings
    from shared.neon.review import (
        get_alerts_by_source_date,
        get_beliefs_for_date,
        get_daily_evaluations,
        get_orphaned_belief_chains,
    )
    from shared.neon.watchlist import get_longterm_watchlist, get_swing_watchlist_with_rsi

    # Verify connectivity
    await fetch_val("SELECT 1")

    query_map: dict[str, Any] = {
        "daily_record": fetch_one(
            "SELECT * FROM daily_records WHERE record_date = $1", target_date
        ),
        "recommendations": get_morning_recommendations(target_date),
        "alerts": get_alerts_by_source_date(target_date),
        "evaluations": get_daily_evaluations(target_date),
        "midday": get_midday_check(target_date),
        "agent_config": _load_agent_configs_from_yaml_async(),
        "watchlist_swing": get_swing_watchlist_with_rsi(),
        "watchlist_longterm": get_longterm_watchlist(),
        "beliefs": get_beliefs_for_date(target_date),
        "belief_accuracy": get_all_belief_accuracy(),
        "belief_orphans": get_orphaned_belief_chains(target_date),
        "belief_unresolved": get_unresolved_beliefs(scan_date=target_date),
        "portfolio": get_portfolio_holdings(),
        "cash": get_cash_balance(),
        # Explicit (ticker, plan_type) grid joined against watchlist ground
        # truth. Since 2026-04-20 ``get_portfolio_holdings`` returns a list of
        # slices directly, but this join still adds the watchlist column for
        # plan-type-rule coherence checks.
        "portfolio_plan_check": _fetch_portfolio_plan_check(target_date),
        "watchlist_membership": _fetch_watchlist_membership(),
    }

    names = list(query_map.keys())
    results = await asyncio.gather(*query_map.values(), return_exceptions=True)
    await close_db()

    return dict(zip(names, results, strict=True))


def fetch_git_fixes(target_date: str, repo_root: str) -> list[dict]:
    """Get same-day git commits with fix detection."""
    fix_keywords = {"fix", "bug", "patch", "hotfix", "revert", "correct", "resolve"}
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--after={target_date}T00:00:00",
                f"--before={target_date}T23:59:59",
                "--all",
                "--format=%H|%h|%s|%an",
                "--stat",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=repo_root,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits: list[dict] = []
        current_commit: dict | None = None
        for line in result.stdout.strip().split("\n"):
            if "|" in line and line.count("|") >= 3:
                parts = line.split("|", 3)
                if len(parts[0]) == 40:  # full hash
                    if current_commit:
                        commits.append(current_commit)
                    message_lower = parts[2].lower()
                    current_commit = {
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "message": parts[2],
                        "author": parts[3],
                        "files_changed": [],
                        "is_fix": any(kw in message_lower for kw in fix_keywords),
                    }
            elif current_commit and " | " in line:
                current_commit["files_changed"].append(line.strip().split(" | ")[0].strip())
        if current_commit:
            commits.append(current_commit)
        return commits
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


LOGFIRE_BASE_URL = "https://logfire-eu.pydantic.dev"
PIPELINE_SPAN_NAMES = (
    "morning_brief_generation",
    "midday_check",
    "retrospective_generation",
    "weekly_watchlist_update",
    "catalyst_check",
    "news_pipeline_v2",
)


def build_logfire_summary(
    spans: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a per-trace summary from raw spans.

    Guarantees consistency with logfire_spans.json because it derives every
    field from the same span list the collector just fetched. Replaces any
    hand-maintained or stale summary so reviews never see diverging counts
    (see MON-2026-04-15-001).
    """
    trace_id_to_name: dict[str, str] = {}
    trace_id_to_duration: dict[str, float] = {}
    for trace in traces:
        trace_id = trace.get("trace_id") or ""
        if not trace_id:
            continue
        trace_id_to_name[trace_id] = trace.get("span_name") or "unknown"
        trace_id_to_duration[trace_id] = float(trace.get("duration") or 0.0)

    # span_id -> agent_name map so broker-tool error rows surface the parent agent
    agent_span_to_name: dict[str, str] = {}

    agent_runs_by_trace: dict[str, list[dict[str, Any]]] = {
        name: [] for name in trace_id_to_name.values()
    }
    tool_exceptions: list[dict[str, Any]] = []
    # Per-agent model_hop_timing outcome counters + retry counters. Surfaces
    # silent-hang recurrence and RetryModel hit-rate for the next
    # pipeline review (MON-2026-04-19-008).
    hop_timing_by_agent: dict[str, dict[str, int]] = {}
    silent_provider_hang_by_agent: dict[str, int] = {}
    hop_retry_by_agent: dict[str, dict[str, int]] = {}
    hop_retry_fail_fast_cluster: int = 0
    hop_retry_agents_seen: set[str] = set()
    # Partial-failure ratio surfaced from phase_parallel_health's span, so the
    # collector summary can carry "degraded morning" evidence alongside
    # silent-hang counts.
    phase2_partial_failure_ratio: float | None = None
    # Broker-tool rows that reported an error_type but were not raised as
    # exceptions — validation errors / schema rejects that tool_exception_count
    # misses entirely.
    tool_errors: list[dict[str, Any]] = []
    # SWI-125 Surface 6: envelope-error tool returns. The broker tool branch
    # often emits `{"error": ...}` / `{"error": ..., "prose": "Failed to ..."}`
    # / bare `"Failed to ..."` strings / `[{"error": ...}]` lists *without*
    # raising — both is_exception and error_type are unset, so tool_errors
    # and tool_exceptions both miss them. The May 12 `statistic.get_stats`
    # TypeError was invisible to the original digest for exactly this reason.
    tool_error_envelopes: list[ToolErrorEnvelope] = []
    tool_error_envelopes_by_agent: dict[str, list[ToolErrorEnvelope]] = {}
    # Null-belief pattern hits grouped by nearest agent-run ancestor. Surfaces
    # belief persistence collapse in the collector manifest in one scan.
    null_belief_hits_by_parent: dict[str, int] = {}
    broker_tool_usage: dict[str, int] = {}
    enrichment_get_flow: list[dict[str, Any]] = []
    all_tool_call_spans: list[dict[str, Any]] = []
    # Per-agent-span chat round tracker for per-round input peak
    # (input_tokens on agent_run is cumulative; chat children show per-call)
    chat_rounds_by_parent: dict[str, list[int]] = {}

    _null_belief_pattern = re.compile(r'"belief"\s*:\s*null')

    # SWI-125 Surface 6 envelope-error detectors. Tool return bodies that
    # surface a failure as data (dict/list/prose) rather than raising.
    # Matches all four observed shapes:
    #   * {"error": ...}                     -> dict envelope, single or
    #   * {'error': ...}                       double quotes accepted.
    #   * {"error": ..., "prose": "Failed to ..."}
    #   * [{"error": ...}, ...]              -> list envelope.
    #   * bare prose "Failed to ..." / "Failed - ..." (alerts.py:281 et al.)
    _envelope_dict_pattern = re.compile(r"""\{\s*['"]error['"]\s*:""")
    _envelope_list_pattern = re.compile(r"""^\s*\[\s*\{\s*['"]error['"]\s*:""")
    _envelope_prose_pattern = re.compile(r"^\s*(Failed to |Failed - )")

    for span in spans:
        attrs = span.get("attributes") or {}
        span_name = span.get("span_name") or ""
        trace_id = span.get("trace_id") or ""
        trace_name = trace_id_to_name.get(trace_id, "unknown")
        is_exception = bool(span.get("is_exception"))
        duration = float(span.get("duration") or 0.0)

        if span_name == "agent run":
            agent_name = attrs.get("agent_name") or attrs.get("gen_ai.agent.name") or "unknown"
            span_id = span.get("span_id") or ""
            if span_id:
                agent_span_to_name[span_id] = str(agent_name)
            agent_runs_by_trace.setdefault(trace_name, []).append(
                {
                    "name": agent_name,
                    "span_id": span_id,
                    "in": attrs.get("gen_ai.usage.input_tokens"),
                    "out": attrs.get("gen_ai.usage.output_tokens"),
                    "dur": round(duration, 2),
                    "exc": is_exception,
                }
            )

        if span_name == "chat":
            parent = span.get("parent_span_id") or ""
            tokens_in = attrs.get("gen_ai.usage.input_tokens")
            if isinstance(tokens_in, int):
                chat_rounds_by_parent.setdefault(parent, []).append(tokens_in)

        if span_name == "model_hop_timing":
            agent_name = str(attrs.get("agent") or "unknown")
            outcome = str(attrs.get("outcome") or "unknown")
            hop_timing_by_agent.setdefault(agent_name, {})
            hop_timing_by_agent[agent_name][outcome] = (
                hop_timing_by_agent[agent_name].get(outcome, 0) + 1
            )

        if span_name == "silent_provider_hang":
            agent_name = str(attrs.get("agent") or attrs.get("agent_name") or "unknown")
            silent_provider_hang_by_agent[agent_name] = (
                silent_provider_hang_by_agent.get(agent_name, 0) + 1
            )

        if span_name == "model_hop_retry":
            agent_name = str(attrs.get("agent") or "unknown")
            outcome = str(attrs.get("outcome") or "unknown")
            hop_retry_by_agent.setdefault(agent_name, {})
            hop_retry_by_agent[agent_name][outcome] = (
                hop_retry_by_agent[agent_name].get(outcome, 0) + 1
            )
            hop_retry_agents_seen.add(agent_name)
            if outcome == "fail_fast_cluster_evidence":
                hop_retry_fail_fast_cluster += 1

        if span_name == "phase2_partial_failure":
            ratio_val = attrs.get("partial_failure_ratio")
            # Prefer the highest ratio across spans (e.g. retro + morning).
            if isinstance(ratio_val, (int, float)) and (
                phase2_partial_failure_ratio is None
                or float(ratio_val) > (phase2_partial_failure_ratio or 0.0)
            ):
                phase2_partial_failure_ratio = float(ratio_val)

        if span_name == "running tool" or span_name.startswith("running tool"):
            tool_name = attrs.get("gen_ai.tool.name") or attrs.get("tool_name") or "unknown"
            tool_arguments = attrs.get("tool_arguments") or {}
            if isinstance(tool_arguments, str):
                # Sometimes serialized; keep raw keys summary only
                args_keys: list[str] = []
            elif isinstance(tool_arguments, dict):
                args_keys = list(tool_arguments.keys())
            else:
                args_keys = []
            all_tool_call_spans.append(
                {
                    "tool": tool_name,
                    "parent_span_id": span.get("parent_span_id"),
                    "trace_id": trace_id,
                    "dur": round(duration, 4),
                    "exc": is_exception,
                }
            )
            if is_exception:
                tool_response = attrs.get("tool_response") or ""
                if isinstance(tool_response, str):
                    trimmed_response = tool_response[:240]
                else:
                    trimmed_response = str(tool_response)[:240]
                tool_exceptions.append(
                    {
                        "tool": tool_name,
                        "span_name": span_name,
                        "trace_id": trace_id,
                        "parent_span_id": span.get("parent_span_id"),
                        "response": trimmed_response,
                        "args_keys": args_keys,
                    }
                )

        # broker tool span (not the LLM-facing "running tool" wrapper)
        broker_tool_name = attrs.get("tool_name")
        if broker_tool_name and "." in str(broker_tool_name):
            name_str = str(broker_tool_name)
            if not is_exception:
                broker_tool_usage[name_str] = broker_tool_usage.get(name_str, 0) + 1
                if name_str == "enrichment.get_flow":
                    enrichment_get_flow.append(
                        {
                            "span_id": span.get("span_id"),
                            "parent_span_id": span.get("parent_span_id"),
                            "dur": round(duration, 2),
                        }
                    )
            # Broker tools sometimes report an error_type without raising —
            # captures validation errors, enum mismatches, half-failures
            # that the is_exception flag alone would miss.
            error_type = attrs.get("error_type") or attrs.get("error") or ""
            if error_type and not is_exception:
                tool_errors.append(
                    {
                        "span_id": span.get("span_id"),
                        "parent_span_id": span.get("parent_span_id"),
                        "tool": name_str,
                        "error_type": str(error_type),
                    }
                )

            # Scan tool output bodies for `"belief":null`; group hits by
            # the nearest agent-run ancestor so reviewers see which
            # sub-agent is emitting nulls.
            tool_output = attrs.get("tool_response") or attrs.get("output") or ""
            if isinstance(tool_output, str) and tool_output:
                null_hits = len(_null_belief_pattern.findall(tool_output))
                if null_hits:
                    parent_id = span.get("parent_span_id") or ""
                    parent_agent = agent_span_to_name.get(parent_id, parent_id or "unknown")
                    null_belief_hits_by_parent[parent_agent] = (
                        null_belief_hits_by_parent.get(parent_agent, 0) + null_hits
                    )

                # SWI-125 Surface 6: envelope-error detection. If the body
                # carries an {"error": ...} dict / list / or starts with
                # "Failed to ..." prose, count it — neither is_exception nor
                # error_type was set, so other counters miss it.
                envelope_kind: EnvelopeKind | None = None
                if _envelope_list_pattern.search(tool_output):
                    envelope_kind = "list"
                elif _envelope_dict_pattern.search(tool_output):
                    envelope_kind = "dict"
                elif _envelope_prose_pattern.search(tool_output):
                    envelope_kind = "prose"
                if envelope_kind is not None:
                    parent_id_env = span.get("parent_span_id") or ""
                    parent_agent_env = agent_span_to_name.get(
                        parent_id_env, parent_id_env or "unknown"
                    )
                    envelope_row: ToolErrorEnvelope = {
                        "tool": name_str,
                        "span_id": span.get("span_id"),
                        "parent_span_id": parent_id_env,
                        "parent_agent": parent_agent_env,
                        "kind": envelope_kind,
                        "response": tool_output[:240],
                    }
                    tool_error_envelopes.append(envelope_row)
                    tool_error_envelopes_by_agent.setdefault(parent_agent_env, []).append(
                        envelope_row
                    )

    # Map parent span_id -> sector_news agent run for per-round peaks
    sector_news_per_round_peaks: list[dict[str, Any]] = []
    for run in agent_runs_by_trace.get("morning_brief_generation", []):
        if run["name"] != "sector_news":
            continue
        span_id = run.get("span_id") or ""
        rounds = chat_rounds_by_parent.get(span_id, [])
        sector_news_per_round_peaks.append(
            {
                "agent_span": span_id,
                "chat_rounds": len(rounds),
                "per_round_peak_input": max(rounds) if rounds else None,
            }
        )

    # Per-agent-run exception roll-up — agent_runs_by_trace already records
    # `exc` per run (line 525); surface as a top-level counter so reviewers
    # see exception volume without walking each trace's run list.
    agent_run_exceptions_by_trace = {
        trace_name: exc_runs
        for trace_name, runs in agent_runs_by_trace.items()
        if (exc_runs := [r for r in runs if r.get("exc")])
    }
    agent_run_exception_count = sum(len(v) for v in agent_run_exceptions_by_trace.values())

    # Per-trace total tokens
    tokens_in_by_trace: dict[str, int] = {}
    tokens_out_by_trace: dict[str, int] = {}
    for trace_name, runs in agent_runs_by_trace.items():
        tokens_in_by_trace[trace_name] = sum(r["in"] for r in runs if isinstance(r.get("in"), int))
        tokens_out_by_trace[trace_name] = sum(
            r["out"] for r in runs if isinstance(r.get("out"), int)
        )

    summary: dict[str, Any] = {
        "generated_by": "scripts/collect_review_data.py:build_logfire_summary",
        "generated_at": datetime.now(VIETNAM_TZ).isoformat(),
        "source_span_count": len(spans),
        "source_trace_count": len(traces),
        "traces": [
            {
                "trace_id": trace_id,
                "name": trace_id_to_name[trace_id],
                "duration_s": round(trace_id_to_duration[trace_id], 2),
            }
            for trace_id in trace_id_to_name
        ],
        "agent_runs_by_trace": agent_runs_by_trace,
        "agent_run_counts_by_trace": {
            name: len(runs) for name, runs in agent_runs_by_trace.items()
        },
        "tokens_in_by_trace": tokens_in_by_trace,
        "tokens_out_by_trace": tokens_out_by_trace,
        "tool_call_count": len(all_tool_call_spans),
        "tool_exception_count": len(tool_exceptions),
        "agent_run_exception_count": agent_run_exception_count,
        "agent_run_exceptions_by_trace": agent_run_exceptions_by_trace,
        "silent_provider_hang_count": sum(silent_provider_hang_by_agent.values()),
        "silent_provider_hang_by_agent": silent_provider_hang_by_agent,
        "tool_exceptions": tool_exceptions,
        "tool_error_count": len(tool_errors),
        "tool_errors": tool_errors,
        "tool_error_envelope_count": len(tool_error_envelopes),
        "tool_error_envelopes": tool_error_envelopes,
        "tool_error_envelopes_by_agent": tool_error_envelopes_by_agent,
        "null_belief_counts": null_belief_hits_by_parent,
        "broker_tool_usage": broker_tool_usage,
        "enrichment_get_flow": enrichment_get_flow,
        "enrichment_get_flow_count": len(enrichment_get_flow),
        "enrichment_get_flow_max_dur": round(
            max((f["dur"] for f in enrichment_get_flow), default=0.0), 2
        ),
        "sector_news_per_round_peaks": sector_news_per_round_peaks,
        "model_hop_timing_by_agent": hop_timing_by_agent,
        "model_hop_retry_by_agent": hop_retry_by_agent,
        "model_hop_retry_agent_count": len(hop_retry_agents_seen),
        "model_hop_retry_fail_fast_cluster_count": hop_retry_fail_fast_cluster,
        "phase2_partial_failure_ratio": phase2_partial_failure_ratio,
    }
    return summary


# (monitoring items constants live near the top of the module; see `copy_monitoring_items`)


_LOGFIRE_LAST_CALL: float = 0.0
_LOGFIRE_RATE_LIMIT_SECS = 16  # Logfire rate limit: sleep 15s between calls


def logfire_query(token: str, sql: str, limit: int = 500) -> list[dict]:
    """Query Logfire REST API, return row-oriented dicts.

    Enforces 16s minimum gap between calls to avoid 429 rate limits.
    """
    import httpx

    global _LOGFIRE_LAST_CALL
    elapsed_since_last = time.monotonic() - _LOGFIRE_LAST_CALL
    if elapsed_since_last < _LOGFIRE_RATE_LIMIT_SECS and _LOGFIRE_LAST_CALL > 0:
        wait = _LOGFIRE_RATE_LIMIT_SECS - elapsed_since_last
        time.sleep(wait)

    resp = httpx.get(
        f"{LOGFIRE_BASE_URL}/v1/query",
        headers={"Authorization": f"Bearer {token}"},
        params={"sql": sql, "limit": str(limit)},
        timeout=30,
    )
    _LOGFIRE_LAST_CALL = time.monotonic()
    resp.raise_for_status()
    col_data = resp.json()

    # Convert column-oriented {columns: [{name, values}, ...]} to row-oriented
    columns = col_data.get("columns", [])
    if not columns:
        return []
    names = [c["name"] for c in columns]
    value_lists = [c["values"] for c in columns]
    row_count = len(value_lists[0]) if value_lists else 0
    return [
        {names[col]: value_lists[col][row] for col in range(len(names))} for row in range(row_count)
    ]


def fetch_logfire_traces(token: str, target_date: str) -> dict[str, Any]:
    """Fetch pipeline traces and spans from Logfire for target_date.

    Uses DataFusion SQL (not PostgreSQL) — no DISTINCT ON support.
    Time-filters via start_timestamp to ensure results are scoped to the target day.
    """
    span_names_sql = ", ".join(f"'{s}'" for s in PIPELINE_SPAN_NAMES)
    window_start_utc, window_end_utc = vietnam_day_utc_window(target_date)

    # Discover traces — match by span_name OR agent_name attribute
    # (midday_check span lives inside async context, discovered via agent_name)
    traces = logfire_query(
        token,
        f"SELECT trace_id, span_name, start_timestamp, end_timestamp, duration "
        f"FROM records "
        f"WHERE (span_name IN ({span_names_sql}) "
        f"  OR (span_name = 'agent run' AND attributes->>'gen_ai.agent.name' IN ('midday', 'alert_registrar'))) "
        f"AND service_name = 'swingy' "
        f"AND start_timestamp >= '{window_start_utc}' "
        f"AND start_timestamp < '{window_end_utc}' "
        f"ORDER BY start_timestamp ASC",
        limit=50,
    )

    # Client-side dedup by trace_id (keep first occurrence per trace)
    seen_trace_ids: set[str] = set()
    day_traces: list[dict] = []
    for trace in traces:
        trace_id = trace.get("trace_id", "")
        if trace_id and trace_id not in seen_trace_ids:
            seen_trace_ids.add(trace_id)
            day_traces.append(trace)

    trace_ids = list(seen_trace_ids)

    if not trace_ids:
        return {"traces": [], "spans": [], "trace_ids": []}

    # Fetch all spans per trace (isolate errors per trace)
    all_spans: list[dict] = []
    for trace_id in trace_ids:
        try:
            spans = logfire_query(
                token,
                f"SELECT trace_id, span_id, parent_span_id, span_name, "
                f"start_timestamp, duration, is_exception, "
                f"attributes "
                f"FROM records "
                f"WHERE trace_id = '{trace_id}' "
                f"AND service_name = 'swingy' "
                f"ORDER BY start_timestamp ASC",
                limit=2000,
            )
            all_spans.extend(spans)
        except Exception as span_error:
            logger.warning("Failed to fetch spans for trace %s: %s", trace_id, span_error)

    return {"traces": day_traces, "spans": all_spans, "trace_ids": trace_ids}


_MAX_FAILED_LOG_FETCHES = 5


def _fetch_gh_failed_step_log(run_id: int, *, max_chars: int = 20_000) -> str:
    """Fetch failed-step logs for a single GH Actions run.

    Added for M7 — without this, pipeline-review subagents can't diagnose
    midday cascading failures (the crash traceback lived only in the GH
    log, not in any JSON artifact the collector shipped).

    Caps output at `max_chars` trailing chars so bundle size stays
    bounded on a long noisy failure.
    """
    try:
        result = subprocess.run(
            ["gh", "run", "view", str(run_id), "--log-failed"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode != 0:
            return f"<gh run view --log-failed failed: {result.stderr.strip()[:200]}>"
        log = result.stdout or ""
        if not log.strip():
            # Runner-acquisition failures (SWI-261) leave no failed-step log
            # because no step ever ran. Fall back to `gh run view` which
            # carries the run-level annotation
            # ("The job was not acquired by Runner of type hosted…").
            try:
                annot = subprocess.run(
                    ["gh", "run", "view", str(run_id)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                annot_text = (annot.stdout or "").strip() or "<empty>"
                # Annotation text usually appears near the top of the
                # output; tail-keep would drop it. Prepend keyword-matched
                # priority lines so they survive truncation.
                keywords = (
                    "not acquired by Runner",
                    "annotation",
                    "Error",
                    "failure",
                    "FAILED",
                )
                priority_lines = [
                    line for line in annot_text.splitlines() if any(kw in line for kw in keywords)
                ][:20]
                preamble = "\n".join(priority_lines)
                budget = max(0, max_chars - len(preamble) - 64)
                tail = annot_text[-budget:] if budget > 0 else ""
                return (
                    "<no failed-step log; runner-acquisition-likely; "
                    "run-level annotations follow>\n"
                    f"{preamble}\n---\n{tail}"
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                return f"<runner-acquisition-likely; gh run view errored: {type(exc).__name__}>"
        if len(log) > max_chars:
            return "<truncated earlier bytes>\n" + log[-max_chars:]
        return log
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return f"<gh run view --log-failed errored: {type(exc).__name__}>"


def fetch_gh_actions(target_date: str, scope: str) -> dict[str, Any]:
    """Fetch GitHub Actions workflow run data.

    Uses a 2-day date range to account for Vietnam (ICT, UTC+7) timezone offset,
    then post-filters by the precise UTC window for the target Vietnam date.

    For failed runs, also fetches `gh run view --log-failed` so the
    pipeline-review subagents can diagnose step-level crashes (M7).
    """
    workflows = SCOPE_TO_WORKFLOWS.get(scope, SCOPE_TO_WORKFLOWS["full"])
    all_runs: list[dict] = []
    all_issues: list[dict] = []

    window_start_utc, window_end_utc = vietnam_day_utc_window(target_date)
    target = date.fromisoformat(target_date)
    yesterday = (target - timedelta(days=1)).isoformat()

    for workflow in workflows:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    f"--workflow={workflow}",
                    f"--created={yesterday}..{target_date}",
                    "--json",
                    "databaseId,status,conclusion,startedAt,updatedAt,headBranch",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                continue
            runs = json.loads(result.stdout)
            for run in runs:
                # Post-filter: only include runs within the Vietnam-day UTC window
                started_at = run.get("startedAt") or ""
                if started_at and not (window_start_utc <= started_at <= window_end_utc):
                    continue
                run["workflow"] = workflow
                all_runs.append(run)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            continue

    # Parallel-fetch failed-step logs. Capped at 5 to keep the collector
    # budget bounded on degenerate days (every workflow failed).
    failed_runs = [
        r
        for r in all_runs
        if r.get("conclusion") == "failure" and isinstance(r.get("databaseId"), int)
    ][:_MAX_FAILED_LOG_FETCHES]
    if failed_runs:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as pool:
            logs = list(pool.map(lambda r: _fetch_gh_failed_step_log(r["databaseId"]), failed_runs))
        for run, log in zip(failed_runs, logs, strict=True):
            run["failed_step_log"] = log

    return {"runs": all_runs, "issues": all_issues}


RESEARCH_ROOT = Path(__file__).parent.parent / "research"

_BRIEF_FILES: tuple[tuple[str, str], ...] = (
    ("morning_brief", "morning-brief.md"),
    ("midday_check", "midday-check.md"),
    ("retrospective", "retrospective.md"),
)

_EMBED_RE = re.compile(r"\[EMBED:[^\]]*\]")
_RR_LITERAL_RE = re.compile(r"R:R\s*>=\s*(\d\.\d)")

# SWI-134: completion sentinel parsing. Producers emit one of these as the
# last line of every brief; absence => incomplete; target_date mismatch =>
# stale checkout (collector ran from a checkout that hadn't pulled).
_COMPLETION_SENTINEL_RE = re.compile(
    r"<!--\s*(?P<kind>MORNING_COMPLETE|MIDDAY_COMPLETE|RETRO_COMPLETE|RETRO_QUARANTINED)"
    r":\s*target_date=(?P<target_date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+run_id=(?P<run_id>\S+))?"
    r"(?:\s+ts=(?P<ts>\S+))?"
    r"\s*-->"
)


def _parse_brief_sections(text: str) -> dict[str, str]:
    """Split a markdown brief into sections keyed by uppercase header.

    Uses the canonical allowlist from `shared.brief_parser.ALL_BRIEF_SECTIONS`
    (which covers morning + retrospective headers). Stanza headers like
    "EVALUATE FPT" or "HOLD ACV [LOW]" are rejected because they are not on
    the allowlist — preventing phantom top-level sections from appearing in
    `markdown_briefs.json`.
    """
    from shared.brief_parser import ALL_BRIEF_SECTIONS, extract_actionable_sections

    return extract_actionable_sections(text, section_names=ALL_BRIEF_SECTIONS)


def fetch_markdown_briefs(target_date: str) -> dict[str, Any]:
    """Parse published markdown briefs for the target date.

    Returns a compact structure (not the full text — bundle size stays
    bounded) with per-section bodies plus pre-computed leak lists so
    subagents can assert on them without re-implementing the regexes:
      - embed_leaks: list of [EMBED: ...] tokens that escaped into the brief
      - rr_literals_by_section: per-section R:R floor literals found
    Added for M7 — without this, subagents could not catch the class of
    bugs fixed in M1/M2/M3 (paraphrase drift, embed leakage, R:R drift).
    """
    briefs: dict[str, Any] = {}
    for key, filename in _BRIEF_FILES:
        path = RESEARCH_ROOT / target_date / filename
        if not path.exists():
            briefs[key] = {"exists": False, "complete": False, "fresh": False}
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            briefs[key] = {
                "exists": True,
                "read_error": str(exc),
                "complete": False,
                "fresh": False,
            }
            continue

        sections = _parse_brief_sections(text)
        embed_leaks = _EMBED_RE.findall(text)
        rr_by_section: dict[str, list[str]] = {}
        for name, body in sections.items():
            hits = _RR_LITERAL_RE.findall(body)
            if hits:
                rr_by_section[name] = hits

        # SWI-134: completion + freshness gates. A producer-side sentinel
        # asserts the file finished writing; target_date asserts the
        # collector and writer agreed on which day's brief this is.
        sentinel_match = _COMPLETION_SENTINEL_RE.search(text)
        complete = sentinel_match is not None
        sentinel_target_date = sentinel_match.group("target_date") if sentinel_match else None
        fresh = bool(sentinel_target_date and sentinel_target_date == target_date)

        try:
            mtime_iso = (
                datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except OSError:
            mtime_iso = None

        briefs[key] = {
            "exists": True,
            "length_chars": len(text),
            "section_count": len(sections),
            "section_names": list(sections.keys()),
            "sections": sections,
            "embed_leaks": embed_leaks,
            "embed_leak_count": len(embed_leaks),
            "rr_literals_by_section": rr_by_section,
            "complete": complete,
            "fresh": fresh,
            "sentinel_target_date": sentinel_target_date,
            "mtime_iso": mtime_iso,
        }
    return briefs


async def main() -> None:
    args = parse_args()
    load_env()
    validate_environment()

    target_date = date.fromisoformat(args.date)
    output_dir = Path(f"/tmp/swingy-review-{args.date}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # SWI-134: pull research/* from origin so the local checkout matches the
    # GH Actions producer push; otherwise we capture the 19:09 stale draft
    # while the published file already has the final brief.
    if args.sync:
        repo_root = str(Path(__file__).parent.parent)
        _sync_research_to_remote(repo_root)

    start_time = time.monotonic()
    errors: list[dict] = []
    manifest_queries: dict[str, dict] = {}

    # Run DB queries
    print(f"Fetching data for {target_date} (scope: {args.scope})...")
    db_results = await fetch_all_db_data(target_date)

    # Write each result to JSON
    for name, result in db_results.items():
        if isinstance(result, BaseException):
            error_entry = {"query": name, "error": str(result)}
            errors.append(error_entry)
            manifest_queries[name] = {"status": "error", "error": str(result)}
            if name in CRITICAL_QUERIES:
                print(f"FATAL: Critical query '{name}' failed: {result}", file=sys.stderr)
                sys.exit(1)
            print(f"  WARNING: {name} failed: {result}")
        else:
            # Convert Record objects to dicts if needed
            if isinstance(result, list):
                data = [dict(r) if hasattr(r, "keys") else r for r in result]
            elif hasattr(result, "keys"):
                data = dict(result)
            else:
                data = result
            row_count = write_json(output_dir, f"{name}.json", data)
            manifest_queries[name] = {"status": "ok", "row_count": row_count}
            print(f"  {name}: {row_count} rows")

    # Belief coverage + per-aggregation weight trace. Derived in-process
    # from the existing get_beliefs_for_date() result — no new SQL.
    beliefs_raw = db_results.get("beliefs")
    if isinstance(beliefs_raw, list):
        beliefs_rows: list[dict] = [
            dict(r) if hasattr(r, "keys") else r
            for r in beliefs_raw
            if isinstance(r, dict) or hasattr(r, "keys")
        ]
        coverage_by_agent = count_coverage_by_agent(beliefs_rows)
        missing_sector = missing_agent_keys(beliefs_rows, EXPECTED_SECTOR_AGENT_KEYS)
        missing_positions = missing_agent_keys(beliefs_rows, EXPECTED_POSITION_AGENT_KEYS)
        aggregation_weights_sample: dict[str, dict[str, float] | dict[str, str]] = {}
        try:
            from agents.belief_aggregation import weighted_aggregate_beliefs_with_weights

            belief_accuracy_raw = db_results.get("belief_accuracy")
            calibration_stats: dict[str, dict] = (
                belief_accuracy_raw if isinstance(belief_accuracy_raw, dict) else {}
            )
            per_ticker: dict[str, list[dict]] = {}
            for row in beliefs_rows:
                ticker = row.get("ticker")
                if ticker:
                    per_ticker.setdefault(str(ticker), []).append(row)
            sample_tickers = [t for t, rows in per_ticker.items() if len(rows) >= 3][:5]
            for ticker in sample_tickers:
                try:
                    _, weights = weighted_aggregate_beliefs_with_weights(
                        per_ticker[ticker], calibration_stats
                    )
                    aggregation_weights_sample[ticker] = weights
                except Exception as agg_err:
                    aggregation_weights_sample[ticker] = {"error": str(agg_err)}
        except ImportError as import_err:
            logger.warning("weight sample skipped (import failure): %s", import_err)

        # SWI-116 / SWI-126: additive review surfacing for per-agent ticker
        # coverage drops and for "ran but persisted nothing" aggregator
        # failures. Existing fields are untouched; downstream consumers
        # under .claude/skills/pipeline-review use ``.get()`` so older
        # bundles keep parsing.
        expected_sector_tickers = frozenset(
            str(r.get("ticker") or "")
            for r in beliefs_rows
            if (r.get("agent_key") or "").startswith("sector_") and r.get("ticker")
        )
        sector_per_agent_missing = per_agent_ticker_coverage(
            beliefs_rows, EXPECTED_SECTOR_AGENT_KEYS, expected_sector_tickers
        )
        sectors_attempted: frozenset[str] = frozenset(
            str(r.get("sector_key") or "")
            for r in beliefs_rows
            if (r.get("agent_key") or "").startswith("sector_") and r.get("sector_key")
        )
        belief_coverage_payload = {
            "belief_coverage_by_agent": coverage_by_agent,
            "missing_sector_agent_keys": missing_sector,
            "missing_position_agent_keys": missing_positions,
            "aggregation_weights_sample": aggregation_weights_sample,
            "per_agent_missing_tickers": sector_per_agent_missing,
            "coverage_degraded_agents": coverage_degraded_agents(
                sector_per_agent_missing, expected_sector_tickers
            ),
            "aggregator_persistence_zero": aggregator_persistence_zero(
                beliefs_rows, SECTOR_AGGREGATOR_KEY, sectors_attempted
            ),
        }
        write_json(output_dir, "belief_coverage.json", belief_coverage_payload, raw=True)
        existing_beliefs_manifest = manifest_queries.get("beliefs") or {}
        existing_beliefs_manifest.update(belief_coverage_payload)
        manifest_queries["beliefs"] = existing_beliefs_manifest
        print(
            f"  belief_coverage: {len(coverage_by_agent)} agent_keys, "
            f"missing_sector={missing_sector or 'none'}, "
            f"missing_positions={missing_positions or 'none'}"
        )

    # Git + GH Actions (sync, fast)
    repo_root = str(Path(__file__).parent.parent)
    git_fixes = fetch_git_fixes(args.date, repo_root)
    write_json(output_dir, "git_fixes.json", git_fixes)
    print(f"  git_fixes: {len(git_fixes)} commits")

    gh_actions = fetch_gh_actions(args.date, args.scope)
    write_json(output_dir, "gh_actions.json", gh_actions)
    failed_with_logs = sum(1 for r in gh_actions.get("runs", []) if r.get("failed_step_log"))
    print(
        f"  gh_actions: {len(gh_actions.get('runs', []))} runs "
        f"(failed-log-bundled={failed_with_logs})"
    )
    manifest_queries["gh_failed_step_logs"] = {
        "status": "ok",
        "row_count": failed_with_logs,
    }

    # Markdown brief ingestion (M7) — parse published research/*.md so
    # reviewers can catch EMBED leakage, verb mismatch, R:R drift from
    # the bundle without re-reading the files.
    markdown_briefs = fetch_markdown_briefs(args.date)
    write_json(output_dir, "markdown_briefs.json", markdown_briefs, raw=True)
    brief_leak_count = sum(
        int(b.get("embed_leak_count") or 0) for b in markdown_briefs.values() if isinstance(b, dict)
    )
    brief_files_present = sum(1 for b in markdown_briefs.values() if b.get("exists"))
    brief_complete = sum(1 for b in markdown_briefs.values() if b.get("complete"))
    brief_fresh = sum(1 for b in markdown_briefs.values() if b.get("fresh"))
    print(
        f"  markdown_briefs: {brief_files_present}/3 files "
        f"(complete={brief_complete}, fresh={brief_fresh}), "
        f"{brief_leak_count} [EMBED:] leaks"
    )
    for key, brief in markdown_briefs.items():
        if brief.get("exists") and not brief.get("fresh"):
            print(
                f"    WARNING: {key} stale or incomplete "
                f"(complete={brief.get('complete')}, "
                f"sentinel_target_date={brief.get('sentinel_target_date')!r}, "
                f"requested={target_date.isoformat()})"
            )
    manifest_queries["markdown_briefs"] = {
        "status": "ok",
        "files_present": brief_files_present,
        "files_complete": brief_complete,
        "files_fresh": brief_fresh,
        "embed_leak_count": brief_leak_count,
    }

    monitoring_entry = copy_monitoring_items(output_dir)
    manifest_queries["monitoring_items"] = dict(monitoring_entry)
    print(
        f"  monitoring_items: open={monitoring_entry['open_items']} "
        f"escalated={monitoring_entry['escalated_items']} "
        f"resolved={monitoring_entry['resolved_items']}"
        + (" (scaffolded fresh)" if monitoring_entry["scaffolded"] else "")
    )

    # Logfire traces (if read token available)
    logfire_token = os.environ.get("LOGFIRE_READ_TOKEN", "")
    if logfire_token:
        try:
            logfire_data = fetch_logfire_traces(logfire_token, args.date)
            write_json(output_dir, "logfire_traces.json", logfire_data["traces"], raw=True)
            write_json(output_dir, "logfire_spans.json", logfire_data["spans"], raw=True)
            # Regenerate summary every run from raw spans so stale files
            # from prior sessions never leak into reviews (MON-2026-04-15-001).
            summary = build_logfire_summary(logfire_data["spans"], logfire_data["traces"])
            write_json(output_dir, "logfire_summary.json", summary, raw=True)
            manifest_queries["logfire_traces"] = {
                "status": "ok",
                "row_count": len(logfire_data["traces"]),
            }
            manifest_queries["logfire_spans"] = {
                "status": "ok",
                "row_count": len(logfire_data["spans"]),
            }
            manifest_queries["logfire_summary"] = {
                "status": "ok",
                "tool_exception_count": summary["tool_exception_count"],
                "agent_run_counts_by_trace": summary["agent_run_counts_by_trace"],
                "enrichment_get_flow_count": summary["enrichment_get_flow_count"],
            }
            trace_count = len(logfire_data["traces"])
            span_count = len(logfire_data["spans"])
            print(
                f"  logfire: {trace_count} traces, "
                f"{span_count} spans, "
                f"summary regenerated "
                f"(exceptions={summary['tool_exception_count']}, "
                f"get_flow={summary['enrichment_get_flow_count']})"
            )

            # Warn about expected-but-missing pipeline traces
            expected_entries = SCOPE_EXPECTED_TRACES.get(args.scope, [])
            found_names = {t.get("span_name", "") for t in logfire_data["traces"]}
            now_vn = datetime.now(VIETNAM_TZ)
            target_is_trading = is_trading_day(date.fromisoformat(args.date))
            for span_name, schedule_ict, trading_day_only in expected_entries:
                if span_name in found_names:
                    continue
                if trading_day_only and not target_is_trading:
                    print(
                        f"  - {span_name} skipped — {args.date} is a "
                        f"VN non-trading day (weekend/holiday)."
                    )
                    continue
                schedule_hour, schedule_min = (int(x) for x in schedule_ict.split(":"))
                scheduled_time = now_vn.replace(
                    hour=schedule_hour, minute=schedule_min, second=0, microsecond=0
                )
                if now_vn < scheduled_time:
                    print(
                        f"  ⚠ {span_name} not found — scheduled at "
                        f"{schedule_ict} ICT (now {now_vn:%H:%M} ICT). "
                        f"Re-run collector after {schedule_ict}."
                    )
                else:
                    print(
                        f"  ⚠ {span_name} MISSING — should have run by "
                        f"{schedule_ict} ICT (now {now_vn:%H:%M} ICT). "
                        f"Check GH Actions for failures."
                    )
        except Exception as logfire_error:
            errors.append({"query": "logfire", "error": str(logfire_error)})
            print(f"  WARNING: Logfire failed: {logfire_error}")
    else:
        print("  logfire: skipped (no LOGFIRE_READ_TOKEN)")

    # Write errors
    if errors:
        write_json(output_dir, "errors.json", errors)

    # Write manifest
    duration = time.monotonic() - start_time
    manifest = {
        "date": args.date,
        "scope": args.scope,
        "created_at": datetime.now(VIETNAM_TZ).isoformat(),
        "duration_seconds": round(duration, 1),
        "files_written": len([f for f in output_dir.iterdir() if f.suffix == ".json"]),
        "failed_queries": len(errors),
        "queries": manifest_queries,
    }
    write_json(output_dir, "manifest.json", manifest)

    print(f"\nDone in {duration:.1f}s -> {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
