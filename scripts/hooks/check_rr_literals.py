"""Pre-commit hook: prevent hardcoded R:R floor literals drifting back in.

2026-04-15 pipeline review (MON-2026-04-16-006): three hardcoded
`R:R >= 3.0` literals in `scripts/agents/synthesis_picks_writer.py` and
one in `scripts/agents/configs/synthesis_picks.yaml` overrode the dynamic
`min_rr_floor` directive, producing a brief that advertised `R:R >= 3.0`
while the retrospective used `R:R >= 3.5`.

Rule (source code): under `scripts/agents/configs/*.yaml` and
`scripts/agents/*.py`, no line may match `R:R\\s*>=\\s*[0-9]\\.[0-9]`
unless the number is wrapped in an f-string expression
(e.g. `R:R >= {floor_str}`).

Rule (generated briefs, 2026-04-22): under `research/*/morning-brief.md`,
the set of forward-looking R:R literals must all match one canonical floor
(or the two-floor pair `effective_rr_floor` + `shock_rr_floor` per
`test_brief_rr_literal_consistency.py`). Retrospective/historical context
sections (MINDSET, NARRATIVE REVIEW, MARKET MOOD "Similar days" lines)
are exempt because they cite past floors, not today's.

Exit-family awareness: ATR_TRAIL recs use `Trail 2.5x ATR` phrasings that
carry no `R:R >=` token; they pass this hook naturally. `exit_fixed_target.py`
and `exit_atr_trail.py` are exempted in case future phrasing uses literal
floors for description hints.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Flag `R:R >= 3.0` (and variants like `R:R >= 3`, `R:R>=3.5`).
LITERAL_PATTERN = re.compile(r"R:R\s*>=\s*(\d+(?:\.\d+)?)")
# Also catch the ≥ glyph and "RR >= X.X" phrasings used in briefs.
BRIEF_LITERAL_PATTERN = re.compile(r"R:R\s*(?:>=|≥)\s*(\d+(?:\.\d+)?)")
# Allow f-string interpolation: `R:R >= {floor_str}` or `R:R >= {min_rr_floor:.1f}`
FSTRING_PATTERN = re.compile(r"R:R\s*>=\s*\{[^}]+\}")

SCAN_GLOBS: tuple[tuple[str, str], ...] = (
    ("scripts/agents/configs/", ".yaml"),
    ("scripts/agents/", ".py"),
)

# Section headers in a morning brief that host historical / retrospective
# commentary where citing a past floor is legitimate. Match against the
# leading tokens on a bare heading line (e.g. "MINDSET", "NARRATIVE REVIEW",
# "## MINDSET") until the next heading.
_RETROSPECTIVE_SECTION_RE = re.compile(
    r"^(?:##\s*)?(MINDSET|NARRATIVE REVIEW|RETROSPECTIVE|PERFORMANCE REVIEW|"
    r"YESTERDAY|PRIOR DAY)\b",
    re.IGNORECASE,
)
# "Similar days" / "n=N" / "prior" lines inside MARKET MOOD etc. cite
# historical R:R used on those days — exempt individually even when the
# surrounding section is forward-looking.
_RETROSPECTIVE_LINE_RE = re.compile(
    r"\b(similar days|n\s*=\s*\d|prior(?: day| session)?|last (?:week|month)|"
    r"yesterday|historical|backtest)\b",
    re.IGNORECASE,
)
# A heading line (all-caps, optional `##` prefix) ends the current section.
_HEADING_LINE_RE = re.compile(r"^(?:##\s+)?[A-Z][A-Z0-9 /]{2,}$")

# Files explicitly exempted — these host conditional shock-phase rules
# or example text that is NOT a live trading floor.
EXEMPT_FILES: frozenset[str] = frozenset(
    {
        # Phase 2 §2.9 — alert_analyst no longer exempt: §2.6 converted its
        # literal to a directive that reads `effective_rr_floor` from the
        # gate. Keep enforcement on so a future literal regression fails.
        # Hook file itself contains the regex as a literal pattern.
        "scripts/hooks/check_rr_literals.py",
        # ExitStrategy impls describe FIXED_TARGET / ATR_TRAIL phrasing;
        # any `R:R` tokens there are display formatters, not live floors.
        "scripts/shared/rules/exit_fixed_target.py",
        "scripts/shared/rules/exit_atr_trail.py",
    }
)


def _line_has_allow_marker(line: str) -> bool:
    """Escape hatch: `# HOOK-ALLOW: rr-literal reason=...` suppresses."""
    return "HOOK-ALLOW: rr-literal" in line


def _scan_file(path: Path, relative: str) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
    except OSError:
        return []

    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not LITERAL_PATTERN.search(line):
            continue
        # Strip any f-string interpolation hit first so the literal regex
        # doesn't double-count a line like `f"R:R >= {x}"`.
        stripped = FSTRING_PATTERN.sub("", line)
        if not LITERAL_PATTERN.search(stripped):
            continue
        if _line_has_allow_marker(line):
            continue
        violations.append(
            (
                lineno,
                f"hardcoded R:R floor literal: {line.strip()!r} — interpolate "
                f"today's directive floor via f-string (e.g. `R:R >= {{floor_str}}`)",
            )
        )
    return violations


def _scan_brief(path: Path, relative: str) -> list[tuple[int, str]]:
    """Scan a generated morning-brief.md for drifted R:R literals.

    Collects forward-looking R:R literals (skipping retrospective sections and
    "similar days" lines). Flags the file if more than two distinct floor
    values appear — the pipeline only sanctions `effective_rr_floor` and
    `shock_rr_floor` per `tests/unit/test_brief_rr_literal_consistency.py`.
    """
    try:
        text = path.read_text()
    except OSError:
        return []

    forward_hits: list[tuple[int, float, str]] = []
    in_retrospective = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped_line = line.strip()
        # Track retrospective-section scope
        if _RETROSPECTIVE_SECTION_RE.match(stripped_line):
            in_retrospective = True
            continue
        if _HEADING_LINE_RE.match(stripped_line) and not _RETROSPECTIVE_SECTION_RE.match(
            stripped_line
        ):
            in_retrospective = False
        if in_retrospective:
            continue
        # Per-line exemption for retrospective phrasing embedded in a
        # forward-looking section (e.g. "Similar days: 75% win rate (n=3)...").
        if _RETROSPECTIVE_LINE_RE.search(stripped_line):
            continue
        if _line_has_allow_marker(line):
            continue
        for match in BRIEF_LITERAL_PATTERN.finditer(stripped_line):
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            forward_hits.append((lineno, value, stripped_line))

    distinct = sorted({value for _, value, _ in forward_hits})
    if len(distinct) <= 2:
        return []

    violations: list[tuple[int, str]] = []
    floors_repr = ", ".join(f"{v:.1f}" for v in distinct)
    for lineno, value, line_text in forward_hits:
        violations.append(
            (
                lineno,
                f"R:R drift in generated brief: literal {value:.1f} "
                f"(floors seen in forward sections: {{{floors_repr}}}) — "
                f"only effective_rr_floor and shock_rr_floor are allowed. "
                f"Line: {line_text!r}",
            )
        )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if raw in EXEMPT_FILES:
            continue
        path = Path(raw)
        if not path.is_file():
            continue

        # Source-code scan (configs + agents)
        source_matched = any(
            raw.startswith(prefix) and raw.endswith(suffix) for prefix, suffix in SCAN_GLOBS
        )
        if source_matched:
            for lineno, message in _scan_file(path, raw):
                all_violations.append((raw, lineno, message))
            continue

        # Generated brief scan
        if raw.startswith("research/") and raw.endswith("/morning-brief.md"):
            for lineno, message in _scan_brief(path, raw):
                all_violations.append((raw, lineno, message))

    if all_violations:
        print(
            "R:R literal lint failed. Hardcoded floors drift away from the "
            "dynamic min_rr_floor directive (MON-2026-04-16-006).",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        print(
            "\nFix: interpolate `{floor_str}` / `{min_rr_floor:.1f}` into the "
            "prompt string, or add exempt path to EXEMPT_FILES if the literal "
            "is a conditional/example value, not a live floor.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
