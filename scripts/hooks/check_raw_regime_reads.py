"""Pre-commit hook: block reads of `regime_raw` outside helpers.py.

`derive_intermediates` in `scripts/pipeline/helpers.py` mutates
`market_level["regime"]` to the post-reconciliation value and preserves the
pre-reconciliation value under `market_level["regime_raw"]`. Every narrative
consumer is expected to read `["regime"]` (the reconciled value). Anything
reading `regime_raw` outside helpers.py is bypassing reconciliation and
reintroduces the regime-split bug (MON-2026-04-22-004).

This hook catches new readers of `regime_raw` at commit time. Whitelist:
`scripts/pipeline/helpers.py` (it IS the producer).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCAN_PREFIXES: tuple[str, ...] = ("scripts/",)
_WHITELIST: frozenset[str] = frozenset(
    {
        "scripts/pipeline/helpers.py",
        "scripts/pipeline/helpers/io.py",  # SWI-212 split of pipeline/helpers.py
        "scripts/pipeline/helpers/derive.py",  # SWI-212 split of pipeline/helpers.py
        "scripts/hooks/check_raw_regime_reads.py",
    }
)
_PATTERN = re.compile(r"regime_raw")


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return []
    if "regime_raw" not in text:
        return []
    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _PATTERN.search(line):
            violations.append(
                (
                    lineno,
                    "reads `regime_raw` — narrative consumers must read the "
                    "reconciled `market_level['regime']`. Raw is producer-only.",
                )
            )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if not any(raw.startswith(prefix) for prefix in SCAN_PREFIXES):
            continue
        normalized = raw.replace("\\", "/")
        if normalized in _WHITELIST:
            continue
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        for lineno, message in _scan_file(path):
            all_violations.append((raw, lineno, message))

    if all_violations:
        print(
            "Raw regime read detected outside pipeline/helpers.py. "
            "The reconciled value lives under `market_level['regime']`; "
            "`regime_raw` is producer-only (see MON-2026-04-22-004).",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
