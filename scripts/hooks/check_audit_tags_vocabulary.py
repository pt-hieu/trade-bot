#!/usr/bin/env python3
"""Pre-commit guard — audit provenance tags must live in the central vocabulary.

Background: `[DERIVED_FROM_BELIEFS]` / `[RECONCILED_FROM_BELIEFS]` are
provenance tags the pipeline writes into recommendation `rationale` /
`verdict` / sector notes so reviewers can audit which reconciliation path
ran. They leaked into the user-facing brief in April 2026; the fix was to
centralize the vocabulary in `scripts/shared/rules/audit_tags.py` and
strip at the render boundary.

This hook catches new `[SOMETHING_FROM_BELIEFS]`-style literals that were
introduced without updating the vocabulary. Every such tag must be
registered in `AUDIT_TAGS` in `audit_tags.py` so `strip_audit_tags` knows
to remove it.

Exit 0: all tags registered. Exit 1: drift found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TAG_PATTERN = re.compile(r"\[[A-Z][A-Z_]*_FROM_BELIEFS\]")
_VOCAB_FILE = Path(__file__).resolve().parents[1] / "shared" / "rules" / "audit_tags.py"

# Callers of this hook pass modified files. The vocabulary file itself AND
# this hook (which cites tag shapes in its docstring) are skipped so their
# self-references aren't flagged as drift.
_SKIP_PATHS = {str(_VOCAB_FILE.resolve()), str(Path(__file__).resolve())}


def _load_vocabulary() -> set[str]:
    text = _VOCAB_FILE.read_text(encoding="utf-8")
    return set(_TAG_PATTERN.findall(text))


def main(files: list[str]) -> int:
    if not files:
        return 0

    vocabulary = _load_vocabulary()
    if not vocabulary:
        print(
            "check-audit-tags-vocabulary: could not load vocabulary from "
            f"{_VOCAB_FILE} — hook misconfigured.",
            file=sys.stderr,
        )
        return 2

    issues: list[str] = []
    for path_str in files:
        resolved = str(Path(path_str).resolve())
        if resolved in _SKIP_PATHS:
            continue
        try:
            text = Path(path_str).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"check-audit-tags-vocabulary: unreadable {path_str}: {exc}", file=sys.stderr)
            continue
        for match in _TAG_PATTERN.finditer(text):
            tag = match.group(0)
            if tag not in vocabulary:
                line_no = text.count("\n", 0, match.start()) + 1
                issues.append(f"{path_str}:{line_no}: {tag} not registered in {_VOCAB_FILE.name}")

    if issues:
        print("Unregistered audit provenance tag(s) found:", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        print(
            "\nAdd the tag to `AUDIT_TAGS` in scripts/shared/rules/audit_tags.py "
            "so `strip_audit_tags` can remove it at the render boundary.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
