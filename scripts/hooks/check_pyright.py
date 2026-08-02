#!/usr/bin/env python3
"""Pre-push hook: run `uv run pyright` and fail on any reported error.

CLAUDE.md Code Quality rule: "Pyright — `uv run pyright` before committing."
Gating at commit time would add ~45s per commit; gating at push time catches
type errors before they reach shared main without slowing the inner loop.

Installed via `.pre-commit-config.yaml` with `stages: [pre-push, manual]`.

Escape hatches: use `# type: ignore[rule]` in source when a third-party stub
forces it. Project-wide excludes live in `pyrightconfig.json` / `[tool.pyright]`
so this script does not need its own allow-list.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    try:
        completed = subprocess.run(
            ["uv", "run", "pyright"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("check_pyright: `uv` not found on PATH.", file=sys.stderr)
        return 1
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
