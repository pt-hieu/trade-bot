"""Pre-commit hook: recommendation rationale must cite only active catalysts / narratives.

Fix 8 of the narrative+catalyst systemic plan (2026-04-21).

Problem the hook prevents:
  The 2026-04-21 audit found 4+ fabricated catalyst citations in
  `daily_recommendations.rationale` text ("Privilege Banking catalyst",
  "Leadership reshuffle", "rubber demand surge") with no matching row in
  `catalysts.event` or `narratives.theme`. Those fabrications slipped
  through review because there was no check that every named catalyst /
  narrative in the rationale text actually existed in the active set for
  that scan date.

How the hook runs:
  1. Walk committed fixtures under `research/rec_citations/*.json`.
  2. Each fixture carries `{active_catalysts: [...], active_narratives: [...],
     recs: [{ticker, rationale}]}` — dumped from a live pipeline run.
  3. For every rec rationale, extract quoted / titled catalyst-style phrases
     and check each against the active sets.
  4. Any un-cited phrase exits non-zero with a precise location report.

Fail-closed: if no fixture is committed the hook exits 0 — the hook only
catches drift when a fixture is provided. Teams who skip dumping fixtures
accept the downside of no local check; a GH-Actions job that runs against
the live DB is the complementary safety net.

Fixture location chosen to avoid coupling with any existing report tree —
`research/rec_citations/` is a fresh namespace.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Fixture root. The hook is forgiving — any JSON under this directory is
# scanned. Committers create subfolders per scan date as they wish.
FIXTURE_ROOT = Path("research/rec_citations")

# Phrases in a rec rationale that *look like* a catalyst/narrative name:
#   - Quoted phrases:  "Fuel-tax cut" or 'PM rate directive'
#   - Title-case run:  Privilege Banking catalyst, Dung Quat refinery
# We only require quoted phrases because title-case runs are noisy. The
# quoted-phrase pattern is deliberately narrow to keep false positives low.
_QUOTED = re.compile(r"[\"“]([A-Za-z][^\"”]{4,60})[\"”]")

# Normaliser for loose matching: lowercase + collapse punctuation/whitespace.
_WORD = re.compile(r"[a-z0-9]+")


def _normalise(text: str) -> frozenset[str]:
    """Return the set of normalised word tokens in the text."""
    return frozenset(_WORD.findall(text.lower()))


def _load_active(fixture: dict) -> list[frozenset[str]]:
    """Build a list of token-sets from `active_catalysts` + `active_narratives`."""
    sources: list[frozenset[str]] = []
    for raw in fixture.get("active_catalysts") or []:
        if isinstance(raw, str):
            sources.append(_normalise(raw))
    for raw in fixture.get("active_narratives") or []:
        if isinstance(raw, str):
            sources.append(_normalise(raw))
    return sources


def _phrase_matches_any(phrase_tokens: frozenset[str], sources: list[frozenset[str]]) -> bool:
    """Require ≥50% of the phrase tokens to overlap with one active source."""
    if not phrase_tokens:
        return True
    for source_tokens in sources:
        overlap = len(phrase_tokens & source_tokens)
        if overlap / len(phrase_tokens) >= 0.5:
            return True
    return False


def _scan_fixture(path: Path) -> list[tuple[str, str, str]]:
    """Return (ticker, phrase, reason) for each un-cited phrase found."""
    try:
        fixture = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as err:
        return [("", "", f"cannot load fixture {path}: {err}")]

    sources = _load_active(fixture)
    if not sources:
        # Empty active set is a fixture configuration error — flag once.
        return [("", "", f"fixture {path} missing active_catalysts + active_narratives")]

    violations: list[tuple[str, str, str]] = []
    for rec in fixture.get("recs") or []:
        ticker = str(rec.get("ticker") or "?")
        rationale = str(rec.get("rationale") or "")
        if not rationale:
            continue
        for quoted_match in _QUOTED.finditer(rationale):
            phrase = quoted_match.group(1).strip()
            tokens = _normalise(phrase)
            if _phrase_matches_any(tokens, sources):
                continue
            violations.append(
                (
                    ticker,
                    phrase,
                    "rationale cites a catalyst/narrative not in the active set — "
                    "likely hallucination",
                )
            )
    return violations


def main(_argv: list[str]) -> int:
    if not FIXTURE_ROOT.exists() or not FIXTURE_ROOT.is_dir():
        # No fixtures committed — hook is a no-op.
        return 0
    all_violations: list[tuple[str, str, str, str]] = []
    for fixture_path in sorted(FIXTURE_ROOT.glob("*.json")):
        for ticker, phrase, reason in _scan_fixture(fixture_path):
            all_violations.append((str(fixture_path), ticker, phrase, reason))

    if not all_violations:
        return 0

    print(
        "Rec rationale citation drift detected (Fix 8, 2026-04-21). "
        "Each rationale must only reference catalysts/narratives present in the "
        "active set for that scan date — fabricated citations were the root cause "
        "of the Apr-21 'Privilege Banking' / 'Leadership reshuffle' hallucinations.",
        file=sys.stderr,
    )
    for fixture_path, ticker, phrase, reason in all_violations:
        print(f"  {fixture_path}  ticker={ticker}  phrase={phrase!r}  {reason}", file=sys.stderr)
    print(
        "\nFix options:\n"
        "  1. Re-run the pipeline and re-dump the fixture with the correct active set.\n"
        "  2. Update the rec rationale to cite an existing catalyst/narrative.\n"
        "  3. Drop the fabricated citation from the rationale.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
