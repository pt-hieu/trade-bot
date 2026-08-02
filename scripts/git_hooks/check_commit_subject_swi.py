#!/usr/bin/env python3
"""commit-msg hook: every non-trivial commit subject names a SWI-NN.

Two-week soft-launch: warns but does not block until cutover_date + 14 days.
After that, escalates to error.

Allow-listed prefixes (subject does NOT need a SWI-NN):
  - `Daily scan: ...`
  - `Weekly watchlist update: ...`
  - `Merge ...`
  - `Revert ...`

Tagged exemptions (`[infra] ...` or `[chore] ...`) are accepted ONLY when the
diff touches none of `scripts/agents/**`, `web/**`, `scripts/db/migrations/**`.
This is the Goodhart guard — using `[chore]` to bypass the rule on a real
agent-prompts change is rejected.

Usage: pre-commit passes the path to .git/COMMIT_EDITMSG as argv[1].
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

CUTOVER_DATE = date(2026, 4, 26)
SOFT_LAUNCH_DAYS = 14
SWI_RE = re.compile(r"\bSWI-\d+\b")
ALLOW_LIST_PREFIXES = ("Daily scan:", "Weekly watchlist update:", "Merge ", "Revert ")
TAG_RE = re.compile(r"^\[(infra|chore)\]", re.IGNORECASE)
PROTECTED_PATHS = (
    "scripts/agents/",
    "web/",
    "scripts/db/migrations/",
)


def _staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _violation(subject: str) -> str | None:
    """Return a one-line violation reason, or None when acceptable."""
    if SWI_RE.search(subject):
        return None
    if any(subject.startswith(prefix) for prefix in ALLOW_LIST_PREFIXES):
        return None
    if TAG_RE.match(subject):
        files = _staged_files()
        offending = [
            file_path
            for file_path in files
            if any(file_path.startswith(p) for p in PROTECTED_PATHS)
        ]
        if offending:
            return (
                f"`[infra]`/`[chore]` tag used but diff touches protected paths: "
                f"{offending[:5]}{' ...' if len(offending) > 5 else ''}. "
                "Use a SWI-NN reference instead."
            )
        return None
    return (
        "Commit subject must reference a Linear ticket (e.g. `SWI-42 :bug: fix(...): ...`) "
        "or be `[infra]`/`[chore]`/`Daily scan:`/`Weekly watchlist update:`/`Merge `/`Revert `."
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("check_commit_subject_swi.py: missing commit-msg path argument", file=sys.stderr)
        return 1

    msg_path = Path(sys.argv[1])
    if not msg_path.exists():
        # pre-commit passes one path per call but for unrelated stages may not point at the
        # commit-msg file — bail silently rather than blocking.
        return 0

    raw = msg_path.read_text(errors="ignore")
    subject = next(
        (line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")),
        "",
    )
    if not subject:
        return 0

    reason = _violation(subject)
    if reason is None:
        return 0

    days_since_cutover = (date.today() - CUTOVER_DATE).days
    if days_since_cutover < SOFT_LAUNCH_DAYS:
        print(
            f"WARN [linear skill, soft-launch ends in "
            f"{SOFT_LAUNCH_DAYS - days_since_cutover} days]: {reason}\n"
            f"Subject: {subject!r}",
            file=sys.stderr,
        )
        return 0

    print(f"ERROR [linear skill]: {reason}\nSubject: {subject!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
