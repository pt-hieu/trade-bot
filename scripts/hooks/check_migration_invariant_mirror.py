"""Pre-commit hook: every new CHECK constraint must have a Python mirror (SWI-NN).

Rule
----
When a migration adds `CHECK (...)` to a table, the same commit must either:

  (a) touch `scripts/shared/rules/row_invariants/{table}.py`, OR
  (b) carry a bypass marker on a line of the SQL file:

      ``# row_invariant_mirror: not_applicable — SWI-NN: <reason>``

      The SWI-NN reference is mandatory. ``SWI-NN`` literal is also accepted as
      a soft-launch placeholder until the real ticket is filed.

Audit mode (`--audit`) reports findings but never fails. Use during the first
week after rollout to surface drift in existing migrations before flipping to
enforce.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TABLE_RE = re.compile(
    r"\b(?:ALTER\s+TABLE|CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?)\s+(?:ONLY\s+)?(\w+)",
    re.IGNORECASE,
)
_CHECK_RE = re.compile(r"\bCHECK\s*\(", re.IGNORECASE)
_BYPASS_RE = re.compile(
    r"row_invariant_mirror:\s*not_applicable\s*[—\-]\s*(SWI-\d+|SWI-NN)\s*:",
    re.IGNORECASE,
)

_INVARIANT_DIR = Path("scripts/shared/rules/row_invariants")


def _extract_tables_with_checks(sql_text: str) -> set[str]:
    """Return tables that gain a CHECK in this SQL.

    Heuristic: split on `;`, scan each statement that mentions CHECK(, capture
    the most recent ALTER/CREATE TABLE target name. Good enough for the
    1-table-per-statement pattern in this repo.
    """
    tables: set[str] = set()
    statements = re.split(r";\s*", sql_text)
    for statement in statements:
        if not _CHECK_RE.search(statement):
            continue
        match = _TABLE_RE.search(statement)
        if match:
            tables.add(match.group(1).lower())
    return tables


def _has_bypass(sql_text: str) -> bool:
    return bool(_BYPASS_RE.search(sql_text))


def _touched_files(argv: list[str]) -> set[str]:
    return {Path(p).as_posix() for p in argv if Path(p).suffix in (".sql", ".py")}


def check_migration(sql_path: Path, touched: set[str]) -> list[str]:
    text = sql_path.read_text()
    tables = _extract_tables_with_checks(text)
    if not tables:
        return []
    if _has_bypass(text):
        return []
    findings: list[str] = []
    for table in tables:
        mirror_relative = (_INVARIANT_DIR / f"{table}.py").as_posix()
        # Allow both repo-rooted ("scripts/...") and absolute / synthetic paths
        # ("/tmp/.../scripts/...") so this hook is testable on synthetic trees.
        if any(p.endswith(mirror_relative) for p in touched):
            continue
        findings.append(
            f"{sql_path}: CHECK on table {table!r} requires a touch to "
            f"{mirror_relative} in the same commit, OR a "
            "`# row_invariant_mirror: not_applicable — SWI-NN: <reason>` marker."
        )
    return findings


def main(argv: list[str]) -> int:
    audit = "--audit" in argv
    args = [a for a in argv if a != "--audit"]
    touched = _touched_files(args)
    findings: list[str] = []
    for arg in args:
        path = Path(arg)
        if path.suffix != ".sql" or not path.exists():
            continue
        if "/migrations/" not in path.as_posix():
            continue
        findings.extend(check_migration(path, touched))
    if findings:
        prefix = "AUDIT" if audit else "Migration invariant-mirror"
        print(f"{prefix} guard findings:")
        for f in findings:
            print(f"  {f}")
        return 0 if audit else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
