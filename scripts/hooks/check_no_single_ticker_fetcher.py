"""Pre-commit hook: flag new single-ticker fetchers without a batch companion.

Single-ticker fetchers (`async def get_*(ticker: str, ...)`) that delegate to
batch-of-1 create pipeline fan-out hazards — the `e37c13a` + `6a5cb7f` batch
migrations removed dozens of these loops. This hook catches recurrence at
commit time so new additions ship with a matching `*_batch` sibling.

Scope: only staged files under `scripts/shared/api/` and `scripts/agents/tools/`.
Pre-existing single-ticker fetchers in untouched files are NOT flagged. Legitimate
exemptions can use the `@allow_single_ticker_fetcher` decorator checked by the
AST walker below.

Batch companion matching uses a stem-token heuristic, not a literal suffix match,
so all three codebase naming conventions work:

- suffix:  `get_financial_ratios` ↔ `get_financial_ratios_batch`
- infix:   `get_ticker_data_async` ↔ `get_batch_ticker_data_async`
- prefix:  `get_ticker_technicals` ↔ `get_batch_ticker_technicals`

A sibling qualifies if its name contains `"batch"` AND shares every meaningful
stem token (after dropping the common `get`/`batch`/`async`/`fetch`/`load` noise).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SCAN_PREFIXES: tuple[str, ...] = (
    "scripts/shared/api/",
    "scripts/agents/tools/",
)

# Stem-token noise to drop before comparing sibling names. Split on `_`.
# "ticker" is structural (describes param shape), drop so flow/insider/data are
# the actual matching signal.
_STEM_NOISE: frozenset[str] = frozenset(
    {"get", "batch", "async", "fetch", "load", "ticker", "tickers"}
)

# Exemption decorator name — add `@allow_single_ticker_fetcher` above a
# legitimate single-ticker-only function (e.g., memoized, vnstock API binds
# single symbol only). Keep rare and justified inline.
_ALLOW_DECORATOR = "allow_single_ticker_fetcher"


def _stem_tokens(name: str) -> frozenset[str]:
    """Split an identifier into meaningful stem tokens."""
    return frozenset(name.lower().split("_")) - _STEM_NOISE


def _has_batch_companion(
    name: str,
    target_stems: frozenset[str],
    batch_stems_by_name: dict[str, frozenset[str]],
) -> bool:
    """Return True iff some batch sibling covers every non-noise stem of `name`.

    Matching rule: a sibling whose name contains "batch" qualifies if its stem
    tokens are a SUPERSET of the target's non-noise stems — the sibling must
    mention every concept the target mentions, not just share one. This avoids
    false negatives like `get_ticker_cash_flow` being shadowed by an unrelated
    `get_batch_flow`. Stems like "ticker"/"get"/"async" are dropped so they
    can't create spurious matches.
    """
    if not target_stems:
        return False
    for other, other_stems in batch_stems_by_name.items():
        if other == name:
            continue
        if target_stems.issubset(other_stems):
            return True
    return False


def _has_allow_decorator(node: ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == _ALLOW_DECORATOR:
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == _ALLOW_DECORATOR:
            return True
    return False


def _first_arg_name(node: ast.AsyncFunctionDef) -> str | None:
    args = node.args.args
    if not args:
        return None
    return args[0].arg


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Single-pass AST walk: collect local names + candidate fetchers together.

    Imports count as local names because a batch companion imported via
    `from shared.api.fundamentals import get_financial_ratios_batch as _get_ratios_batch`
    creates a local binding that legitimately satisfies the companion requirement.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []

    local_names: set[str] = set()
    candidates: list[ast.AsyncFunctionDef] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            local_names.add(node.name)
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name.startswith("get_")
                and not node.name.endswith("_batch")
                and _first_arg_name(node) == "ticker"
                and not _has_allow_decorator(node)
            ):
                candidates.append(node)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_names.add(alias.asname or alias.name.split(".")[0])

    if not candidates:
        return []

    # Precompute stem sets once per file so _has_batch_companion is O(siblings),
    # not O(candidates × siblings × tokenize_cost). Only "batch"-containing
    # names are companion candidates — filter early.
    batch_stems_by_name: dict[str, frozenset[str]] = {
        name: _stem_tokens(name) for name in local_names if "batch" in name.lower()
    }

    violations: list[tuple[int, str]] = []
    for node in candidates:
        target_stems = _stem_tokens(node.name)
        if _has_batch_companion(node.name, target_stems, batch_stems_by_name):
            continue
        violations.append((node.lineno, node.name))
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if not any(raw.startswith(prefix) for prefix in SCAN_PREFIXES):
            continue
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        for lineno, name in _scan_file(path):
            all_violations.append((raw, lineno, name))

    if all_violations:
        print(
            "Single-ticker fetchers without a *_batch companion found. "
            "Add a matching batch function in the same module, or mark "
            f"the fetcher with @{_ALLOW_DECORATOR} + an inline justification.",
            file=sys.stderr,
        )
        for relative_path, lineno, name in all_violations:
            print(
                f"  {relative_path}:{lineno}  async def {name}(ticker: str, ...)",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
