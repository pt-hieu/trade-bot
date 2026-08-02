"""Pre-commit hook: block broad ``except Exception`` swallow patterns in neon.

Why this exists
---------------
``scripts/shared/neon/*.py`` writers historically swallowed all exceptions
with::

    except Exception as e:
        logger.warning(...)
        return False

That masks key contract bugs, enum drift, and business-logic
``RuntimeError`` (e.g. the 2026-04-19 retro evaluator persistence gap).
Real connectivity errors should funnel through
``shared.neon._error_guard.narrow_db_error`` instead.

Rule
----
Inside ``scripts/shared/neon/`` (recursively, including ``insert_records/``):

  * ``except Exception`` / ``except (Exception, ...)`` handlers are
    flagged unless their body calls ``narrow_db_error(...)`` or re-raises
    the original exception.
  * The helper file ``_error_guard.py`` is exempt — it defines the allowlist.

Run::

    uv run python scripts/hooks/check_broad_except_in_neon.py <files...>
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

NEON_PREFIX = "scripts/shared/neon/"
EXEMPT_FILENAMES = {"_error_guard.py"}

# Legacy allowlist: files NOT yet migrated to narrow_db_error. Cleanup
# debt tracked under issues/active/ (Group 12 follow-up).
# Adding a new entry here requires a comment justifying why a sweep migration
# would be too risky in the same commit. Removing is preferred — when a
# legacy file gets touched for any reason, migrate its handlers in the same
# diff and drop it from this set.
LEGACY_ALLOWLIST: set[str] = {
    "scripts/shared/neon/insert_strategy_insights.py",
    "scripts/shared/neon/memory.py",
    "scripts/shared/neon/insert_content.py",
    # SWI-197 split: code moved unchanged from insert_content.py. Carries
    # the same legacy except-pattern; no new violations introduced.
    "scripts/shared/neon/insert_midday.py",
    "scripts/shared/neon/update_content.py",
    "scripts/shared/neon/checkpoints.py",
    "scripts/shared/neon/insert_scan.py",
    "scripts/shared/neon/watchlist.py",
    "scripts/shared/neon/directives.py",
    "scripts/shared/neon/insert_learnings.py",
    "scripts/shared/neon/position_alerts.py",
    "scripts/shared/neon/portfolio.py",
    "scripts/shared/neon/insert_market.py",
    "scripts/shared/neon/portfolio_trades.py",
    "scripts/shared/neon/longterm.py",
    "scripts/shared/neon/learnings.py",
    "scripts/shared/neon/alerts.py",
    "scripts/shared/neon/alert_lifecycle.py",
    "scripts/shared/neon/articles.py",
    "scripts/shared/neon/beliefs.py",
    "scripts/shared/neon/belief_queries.py",
    "scripts/shared/neon/catalyst_signals.py",
    "scripts/shared/neon/catalyst_summaries.py",
    "scripts/shared/neon/company_profiles.py",
    "scripts/shared/neon/earnings.py",
    "scripts/shared/neon/enrichment.py",
    "scripts/shared/neon/ensemble.py",
    "scripts/shared/neon/flow.py",
    "scripts/shared/neon/market.py",
    "scripts/shared/neon/narrative_summaries.py",
    "scripts/shared/neon/pending_evals.py",
    "scripts/shared/neon/review.py",
    "scripts/shared/neon/advocate_reviews.py",
    # Priority migration sites (Group 12 plan); migrated opportunistically
    # rather than in one giant sweep. Removed from this set as each site
    # is touched. insert_records/daily.py + morning.py are removed by
    # Group 3 (retro fail-loud).
    "scripts/shared/neon/catalysts.py",
    "scripts/shared/neon/narratives.py",
    "scripts/shared/neon/insert_evaluations.py",
    # daily.py + morning.py removed by Group 3 (retro fail-loud).
    "scripts/shared/neon/insert_records/votes.py",
    "scripts/shared/neon/insert_records/continuity.py",
}


def _handler_catches_bare_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
        return True
    if isinstance(handler.type, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id == "Exception" for elt in handler.type.elts)
    return False


def _handler_is_compliant(handler: ast.ExceptHandler) -> bool:
    """Return True when the body uses narrow_db_error or re-raises.

    Compliance forms:
      narrow_db_error(exc, context="...")
      raise / raise <expr>
    """
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "narrow_db_error"
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "narrow_db_error"
        ):
            return True
    return False


def check_file(path: Path) -> list[str]:
    if path.name in EXEMPT_FILENAMES:
        return []
    posix = path.as_posix()
    if posix in LEGACY_ALLOWLIST:
        return []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: syntax error: {e.msg}"]

    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _handler_catches_bare_exception(node):
            continue
        if _handler_is_compliant(node):
            continue
        findings.append(
            f"{path}:{node.lineno}: broad `except Exception` without "
            f"narrow_db_error()/re-raise. Use shared.neon._error_guard.narrow_db_error."
        )
    return findings


def main(argv: list[str]) -> int:
    findings: list[str] = []
    for arg in argv:
        path = Path(arg)
        if not str(path).startswith(NEON_PREFIX):
            continue
        if path.suffix != ".py":
            continue
        if not path.exists():
            continue
        findings.extend(check_file(path))

    if findings:
        print("Broad-except guard violations:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
