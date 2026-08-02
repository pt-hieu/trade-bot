"""
Midday check output formatting — markdown generation and file persistence.
"""

import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

RESEARCH_DIR = Path(__file__).parent.parent.parent / "research"


def _midday_sentinel(target_date: str) -> str:
    """SWI-134 trailer for completion + freshness detection."""
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ.get("LOGFIRE_TRACE_ID") or "local"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"\n<!-- MIDDAY_COMPLETE: target_date={target_date} run_id={run_id} ts={ts} -->\n"


def format_afternoon_plan_prose(plan: Iterable[dict] | None, note: str | None = None) -> str:
    """Render a structured afternoon_plan list (migration 316) as readable prose.

    Replaces every historical `(afternoon_plan or "N/A")` consumer. Each entry
    becomes a `- ACTION TICKER [CONFIDENCE]: reason` line; orphaned NOTE
    entries (legacy-seeded rows with ticker=None) render without the ticker.
    An optional `note` is appended as a trailing paragraph.
    """
    lines: list[str] = []
    for entry in plan or []:
        if not isinstance(entry, dict):
            continue
        action = (entry.get("action") or "NOTE").upper()
        confidence = (entry.get("confidence") or "LOW").upper()
        ticker = entry.get("ticker")
        reason = (entry.get("reason") or "").strip() or "(no reason provided)"
        header = f"{action} {ticker}" if ticker else action
        lines.append(f"- {header} [{confidence}]: {reason}")
    if note:
        note_clean = note.strip()
        if note_clean:
            if lines:
                lines.append("")
            lines.append(note_clean)
    return "\n".join(lines) if lines else "N/A"


# Sections generate_midday_markdown ALWAYS emits for a real analysis run.
# Entries Hit / Big Movers / Position Alerts are conditional and intentionally
# omitted from this floor so quiet-but-valid days do not trip the gate.
_MIDDAY_REQUIRED_SECTIONS = (
    "## Trading Mode",
    "## Morning Reflection",
    "## Afternoon Plan",
)


def validate_midday_markdown(markdown: str) -> list[str]:
    """Section-count gate for the rendered midday markdown (SWI-235).

    Mirrors ``agents.synthesis_validators.validate_synthesis_output`` for the
    morning brief: a real analysis run must carry the mandatory sections. A
    markdown missing any of them is a degenerate render (empty/malformed LLM
    result) and is distinguishable from a deliberate skip-stub. Advisory only —
    returns warnings; the caller logs and ships (exit-0 policy, MON-2026-04-16-001).
    """
    warnings: list[str] = []
    if not markdown or not markdown.strip():
        warnings.append("MIDDAY OUTPUT EMPTY: rendered markdown is blank")
        return warnings
    missing = [section for section in _MIDDAY_REQUIRED_SECTIONS if section not in markdown]
    if missing:
        warnings.append(
            f"MIDDAY SECTION GAP: rendered markdown missing required sections: {', '.join(missing)}"
        )
    return warnings


def generate_midday_markdown(result: dict, date_str: str) -> str:
    """Generate markdown output from midday check result."""
    lines = [
        f"# Midday Market Check - {date_str}",
        "",
        f"*Generated at {datetime.now().strftime('%H:%M:%S')} (market break)*",
        "",
        "---",
        "",
        f"## Trading Mode: {result['trading_mode']}",
        "",
        result["capital_note"],
        "",
        "---",
        "",
        "## Morning Reflection",
        "",
        result["morning_reflection"],
        "",
    ]

    # Entries hit section
    entries = result.get("entries_hit", [])
    if entries:
        lines.extend(
            [
                "---",
                "",
                "## Entries Hit",
                "",
                "| Ticker | Recommended | Actual Low | Current | Status |",
                "|--------|-------------|------------|---------|--------|",
            ]
        )
        for e in entries:
            lines.append(
                f"| {e['ticker']} | {e['recommended_entry']:,.0f} | "
                f"{e['actual_low']:,.0f} | {e['current_price']:,.0f} | {e['status']} |"
            )
        lines.append("")

    # Big movers section
    movers = result.get("big_movers", [])
    if movers:
        lines.extend(
            [
                "---",
                "",
                "## Big Movers (+/- 3%)",
                "",
                "| Ticker | Open | Current | Change |",
                "|--------|------|---------|--------|",
            ]
        )
        for m in movers:
            sign = "+" if m["change_pct"] >= 0 else ""
            lines.append(
                f"| {m['ticker']} | {m['open_price']:,.0f} | "
                f"{m['current_price']:,.0f} | {sign}{m['change_pct']:.1f}% |"
            )
        lines.append("")

    # Position alerts section
    alerts = result.get("position_alerts", [])
    if alerts:
        lines.extend(
            [
                "---",
                "",
                "## Position Alerts",
                "",
                "| Ticker | Current | Level | Type | Distance | Urgency |",
                "|--------|---------|-------|------|----------|---------|",
            ]
        )
        for a in alerts:
            lines.append(
                f"| {a['ticker']} | {a['current_price']:,.0f} | "
                f"{a['level']:,.0f} | {a['level_type']} | "
                f"{a['distance_pct']:.1f}% | {a['urgency']} |"
            )
        lines.append("")

    # Afternoon plan
    lines.extend(
        [
            "---",
            "",
            "## Afternoon Plan",
            "",
            format_afternoon_plan_prose(
                result.get("afternoon_plan") or [],
                result.get("afternoon_note"),
            ),
            "",
        ]
    )

    return "\n".join(lines)


def save_midday_check(content: str, date_str: str) -> Path:
    """Save midday check to research directory.

    Atomic write + MIDDAY_COMPLETE sentinel (SWI-134).
    """
    output_dir = RESEARCH_DIR / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "midday-check.md"
    body = content + _midday_sentinel(date_str)
    tmp_path = output_file.with_suffix(output_file.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp_path, output_file)

    print(f"  Saved: {output_file}")
    return output_file
