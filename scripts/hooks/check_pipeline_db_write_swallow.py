"""Pre-commit hook: pipeline DB-write `except Exception` swallow guard (SWI-NN).

Scope: `scripts/pipeline/*.py`, `scripts/db/*.py`, `scripts/agents/*persist*.py`.

Detection
---------
A broad `except Exception` handler is flagged when its body:
  (a) imports or calls a name from `shared.neon`, OR
  (b) returns False / None / [] (legacy `narrow_db_error`-style helpers that
      don't re-raise).

Compliance
----------
At least one of:
  - explicit `raise` (re-raise the caught exception),
  - call to `narrow_db_error(...)`,
  - env-gated raise (`if os.environ.get("SWINGY_ENV") != "production": raise`),
  - LEGACY_ALLOWLIST entry naming the file path.

Delineation from siblings
-------------------------
- `check_broad_except_in_neon.py` — covers `shared/neon/`. Disjoint scope.
- `check_no_silent_swallow.py` — `except Exception: print(...)` pattern.
- `check_swallow_pattern.py` — typed-exception ordering around `wait_for`.
This hook closes the pipeline/db swallow class those three do not cover.

Run::

    uv run python scripts/hooks/check_pipeline_db_write_swallow.py [--audit] <files...>
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_SCAN_PREFIXES: tuple[str, ...] = (
    "scripts/pipeline/",
    "scripts/db/",
)
_AGENT_PERSIST_SUFFIX = "persist.py"


# Files NOT yet migrated. Adding an entry requires a SWI-NN comment in the
# adjacent commit naming the migration follow-up. Prefer migrating in place.
LEGACY_ALLOWLIST: set[str] = {
    # SWI-308: `save_catalyst_news_signals` is a non-load-bearing observability
    # write — failure must not crash the morning pipeline. The handler emits
    # `log_warn("CATALYST_SIGNAL_BATCH_SAVE_FAILED", ...)` so the [MON]
    # regression-watch picks it up. Migrate when the writer becomes load-bearing.
    "scripts/pipeline/catalyst_news_check.py",
}


def _in_scope(path: Path) -> bool:
    posix = path.as_posix()
    if any(posix.startswith(p) for p in _SCAN_PREFIXES):
        return True
    return posix.startswith("scripts/agents/") and posix.endswith(_AGENT_PERSIST_SUFFIX)


def _handler_catches_bare_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
        return True
    if isinstance(handler.type, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id == "Exception" for elt in handler.type.elts)
    return False


def _body_references_neon(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Attribute):
            chain: list[str] = []
            cur: ast.AST = node
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                chain.append(cur.id)
            if "neon" in chain:
                return True
        if isinstance(node, ast.Name) and node.id == "narrow_db_error":
            return True
    return False


def _body_returns_sentinel(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Return):
            val = node.value
            if val is None:
                return True
            if isinstance(val, ast.Constant) and val.value in (False, None):
                return True
            if isinstance(val, ast.List) and not val.elts:
                return True
    return False


def _handler_is_compliant(handler: ast.ExceptHandler, source_lines: list[str]) -> bool:
    has_raise = False
    has_narrow = False
    has_env_gated_raise = False
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            has_raise = True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "narrow_db_error"
        ):
            has_narrow = True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "narrow_db_error"
        ):
            has_narrow = True
    # env-gated raise: scan source between handler.lineno and end_lineno for
    # `SWINGY_ENV` + `raise`.
    start = handler.lineno - 1
    end = handler.end_lineno or len(source_lines)
    snippet = "\n".join(source_lines[start:end])
    if "SWINGY_ENV" in snippet and "raise" in snippet:
        has_env_gated_raise = True
    return has_raise or has_narrow or has_env_gated_raise


def check_file(path: Path) -> list[str]:
    posix = path.as_posix()
    if not _in_scope(path):
        return []
    if posix in LEGACY_ALLOWLIST:
        return []
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: syntax error: {e.msg}"]
    source_lines = text.splitlines()
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _handler_catches_bare_exception(node):
            continue
        suspect = _body_references_neon(node) or _body_returns_sentinel(node)
        if not suspect:
            continue
        if _handler_is_compliant(node, source_lines):
            continue
        findings.append(
            f"{path}:{node.lineno}: broad `except Exception` swallows a DB write "
            f"without raise/narrow_db_error/env-gated raise. "
            f"Use `if os.environ.get('SWINGY_ENV') != 'production': raise` or "
            f"`narrow_db_error(exc, context=...)`."
        )
    return findings


def main(argv: list[str]) -> int:
    audit = "--audit" in argv
    args = [a for a in argv if a != "--audit"]
    findings: list[str] = []
    for arg in args:
        path = Path(arg)
        if path.suffix != ".py" or not path.exists():
            continue
        findings.extend(check_file(path))
    if findings:
        prefix = "AUDIT" if audit else "Pipeline DB-write swallow"
        print(f"{prefix} guard findings:")
        for f in findings:
            print(f"  {f}")
        return 0 if audit else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
