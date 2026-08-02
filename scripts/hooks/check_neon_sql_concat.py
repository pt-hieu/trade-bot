#!/usr/bin/env python3
"""Guard against implicit string-literal concat building Neon SQL.

The matcher is tokenize-based (PEP 701 f-strings emit STRING + FSTRING_START,
which a regex pair would miss) and refuses to start unless its self-test
flags the canonical bug pattern verbatim — tamper-evident.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

from _common import iter_python_files, line_has_allow_marker

REPO_ROOT = Path(__file__).resolve().parents[2]
NEON_SCOPE = "scripts/shared/neon/"
ALLOW_MARKER = "HOOK-ALLOW: neon-sql-concat"

TRIGGER_PREFIXES = ("AND", "OR", "WHERE", "JOIN", "SELECT", "LIMIT", "ORDER", "GROUP")

FSTRING_START_TYPE = getattr(tokenize, "FSTRING_START", -1)
FSTRING_MIDDLE_TYPE = getattr(tokenize, "FSTRING_MIDDLE", -1)
FSTRING_END_TYPE = getattr(tokenize, "FSTRING_END", -1)


def _is_string_start(token: tokenize.TokenInfo) -> bool:
    return token.type == tokenize.STRING or token.type == FSTRING_START_TYPE


def _leading_literal(tokens: list[tokenize.TokenInfo], index: int) -> str:
    token = tokens[index]
    if token.type == tokenize.STRING:
        try:
            return str(ast.literal_eval(token.string))
        except (SyntaxError, ValueError):
            return token.string
    if token.type == FSTRING_START_TYPE and index + 1 < len(tokens):
        next_token = tokens[index + 1]
        if next_token.type == FSTRING_MIDDLE_TYPE:
            return next_token.string
    return ""


def _ends_with_separator(text: str) -> bool:
    return bool(text) and text[-1] in (" ", "\n", "\t")


def find_violations(source: str, file_path: str) -> list[str]:
    """Return human-readable violation strings for ``source``."""
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(source.encode("utf-8")).readline))
    except (tokenize.TokenError, SyntaxError) as exc:
        return [f"{file_path}: tokenize failed: {exc}"]

    source_lines = source.splitlines()
    violations: list[str] = []
    token_count = len(tokens)
    index = 0
    while index < token_count:
        prev_token = tokens[index]
        if not _is_string_start(prev_token):
            index += 1
            continue

        prev_literal_full = ""
        if prev_token.type == tokenize.STRING:
            try:
                prev_literal_full = str(ast.literal_eval(prev_token.string))
            except (SyntaxError, ValueError):
                prev_literal_full = ""
            after_prev_index = index + 1
        else:
            after_prev_index = index + 1
            last_middle = ""
            while (
                after_prev_index < token_count and tokens[after_prev_index].type != FSTRING_END_TYPE
            ):
                if tokens[after_prev_index].type == FSTRING_MIDDLE_TYPE:
                    last_middle = tokens[after_prev_index].string
                after_prev_index += 1
            after_prev_index += 1  # skip FSTRING_END
            prev_literal_full = last_middle

        if not prev_literal_full or _ends_with_separator(prev_literal_full):
            index = after_prev_index
            continue

        next_significant_index = after_prev_index
        while next_significant_index < token_count and tokens[next_significant_index].type in (
            tokenize.NL,
            tokenize.COMMENT,
        ):
            next_significant_index += 1
        if next_significant_index >= token_count or not _is_string_start(
            tokens[next_significant_index]
        ):
            index = after_prev_index
            continue

        next_literal_raw = _leading_literal(tokens, next_significant_index)
        if not next_literal_raw:
            index = after_prev_index
            continue
        if next_literal_raw[0] in (" ", "\n", "\t"):
            index = next_significant_index
            continue
        next_literal_lstripped = next_literal_raw.lstrip()
        if any(next_literal_lstripped.startswith(prefix) for prefix in TRIGGER_PREFIXES):
            line_number = prev_token.start[0]
            allow_end_line = tokens[next_significant_index].end[0]
            if not line_has_allow_marker(source_lines, line_number, allow_end_line, ALLOW_MARKER):
                violations.append(
                    f"{file_path}:{line_number}: implicit string concat builds SQL — "
                    f"prior literal ends with {prev_literal_full[-20:]!r}, "
                    f"next literal starts with {next_literal_lstripped[:24]!r}. "
                    f"Bind via $N positional parameter instead."
                )
        index = next_significant_index

    return violations


# Self-test fixtures reproduce the canonical narratives.py:34→35 bug verbatim
# so any future refactor of _leading_literal / find_violations that breaks the
# matcher fails at hook boot.
_SELF_TEST_BUG = (
    "freshness_clause = (\n"
    "    \"AND last_seen >= CURRENT_DATE - INTERVAL '7 days' \"\n"
    '    "AND array_length(affected_tickers, 1) > 0"\n'
    "    f\"AND pipeline_version = '{PIPELINE_VERSION_V2}'\"\n"
    ")\n"
)

_SELF_TEST_OK_TRIPLE = (
    'sql = """SELECT a, b FROM t\n         WHERE x = $1\n           AND y = $2"""\n'
)


def _run_self_test() -> None:
    if not find_violations(_SELF_TEST_BUG, "<self-test-bug>"):
        sys.stderr.write(
            "check_neon_sql_concat self-test FAILED: matcher did not flag "
            "the canonical narratives.py:34→35 pattern.\n"
        )
        sys.exit(2)
    false_positives = find_violations(_SELF_TEST_OK_TRIPLE, "<self-test-ok>")
    if false_positives:
        sys.stderr.write(
            "check_neon_sql_concat self-test FAILED: false-positive on "
            f"single triple-quoted SQL: {false_positives}\n"
        )
        sys.exit(2)


def main() -> int:
    _run_self_test()
    if len(sys.argv) > 1:
        targets = [Path(arg) for arg in sys.argv[1:] if arg.endswith(".py")]
    else:
        targets = iter_python_files(REPO_ROOT, scopes=[NEON_SCOPE])

    all_violations: list[str] = []
    for path in targets:
        if not path.exists():
            continue
        if NEON_SCOPE.rstrip("/") not in path.as_posix():
            continue
        source = path.read_text(encoding="utf-8")
        all_violations.extend(find_violations(source, path.as_posix()))

    if all_violations:
        sys.stderr.write("\n".join(all_violations) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(main())
