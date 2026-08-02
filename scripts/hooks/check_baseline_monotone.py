#!/usr/bin/env python3
"""Pre-commit hook: block silent inflation of grandfathered baselines.

CLAUDE.md develops on ``main`` directly (no PR review). Without this guard,
an accidental ``--regenerate`` could raise a baseline count and mask the
regression the hook was meant to catch. This check compares every
``scripts/hooks/data/*_baseline.txt`` against its ``HEAD`` counterpart (the
last committed version; staged baselines have not landed yet at pre-commit
time) and fails when:

- A path's count grew vs the prior revision, OR
- A path was added and the current count is higher than zero.

Legitimate baseline regeneration is explicit: include
``baseline-regen: <file>`` somewhere in the commit message to skip the check
for that baseline file. Example commit msg:

    refactor: split technicals.py into three modules

    baseline-regen: max_lines_baseline.txt

Escape hatches:
- Commit-message token ``baseline-regen: <baseline basename>``.
- ``EXEMPT_FILES`` for baselines that we never want to gate (empty today).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._baseline import load_baseline, parse_baseline_text  # noqa: E402

EXEMPT_FILES: frozenset[str] = frozenset()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINE_DIR = _REPO_ROOT / "scripts" / "hooks" / "data"

_REGEN_TOKEN_RE = re.compile(r"baseline-regen:\s*(\S+)")


def _git_show(revision: str, path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _collect_regen_tokens() -> set[str]:
    """Read baseline-regen tokens from the commit message when available."""
    tokens: set[str] = set()
    commit_msg_path = os.environ.get("COMMIT_MSG_FILE") or os.environ.get(
        "PRE_COMMIT_COMMIT_MSG_FILE"
    )
    if commit_msg_path:
        try:
            msg = Path(commit_msg_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            msg = ""
        for match in _REGEN_TOKEN_RE.finditer(msg):
            tokens.add(match.group(1).strip())
    env_token = os.environ.get("BASELINE_REGEN")
    if env_token:
        for tok in env_token.split(","):
            tokens.add(tok.strip())
    return {tok for tok in tokens if tok}


def _selected_baselines(argv: list[str]) -> list[Path]:
    if len(argv) > 1:
        paths: list[Path] = []
        for raw in argv[1:]:
            path = Path(raw)
            if not path.is_absolute():
                path = _REPO_ROOT / path
            if path.exists() and path.suffix == ".txt" and "_baseline" in path.name:
                paths.append(path)
        return paths
    return sorted(_BASELINE_DIR.glob("*_baseline.txt"))


def main(argv: list[str]) -> int:
    regen_tokens = _collect_regen_tokens()
    failures: list[str] = []
    for path in _selected_baselines(argv):
        rel = str(path.relative_to(_REPO_ROOT))
        if rel in EXEMPT_FILES:
            continue
        if path.name in regen_tokens or rel in regen_tokens:
            continue
        current = load_baseline(path)
        previous_text = _git_show("HEAD", rel)
        if previous_text is None:
            # First commit of this baseline — nothing to regress against.
            continue
        previous = parse_baseline_text(previous_text)
        for key, curr_count in sorted(current.items()):
            prev_count = previous.get(key)
            if prev_count is None:
                if curr_count > 0:
                    failures.append(f"  {rel}: {key} newly added at count {curr_count}")
            elif curr_count > prev_count:
                failures.append(f"  {rel}: {key} grew {prev_count} → {curr_count}")
    if failures:
        print(
            "Baseline inflation detected. Fix the regression or commit with "
            "`baseline-regen: <baseline_filename>` in the commit message.",
            file=sys.stderr,
        )
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
