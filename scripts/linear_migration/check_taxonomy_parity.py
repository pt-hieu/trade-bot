#!/usr/bin/env python3
"""Pre-commit hook: labels.json category/severity/dimension keys must match the
findings_schema.py enums in both directions.

Drift-class fix. The new `linear` skill cites these enums + JSON as the canonical
list of category/severity/dimension values. Any time the skill's prose references
a value, it must exist in both the JSON (for Linear UUID lookup) and the enum
(for Pydantic validation). This guard fails loud on missing-from-either-side so
the skill, the write-back, and the Linear workspace stay in sync.

Runs full-tree (`pass_filenames: false`) — parity is a global property between
two files; a single-file diff can drift one without the other.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.linear_migration.client import load_labels_json  # noqa: E402
from scripts.linear_migration.findings_schema import (  # noqa: E402
    FindingCategory,
    FindingDimension,
    FindingSeverity,
)

GROUP_ENUM_MAP: dict[str, type] = {
    "category": FindingCategory,
    "severity": FindingSeverity,
    "dimension": FindingDimension,
}


def _enum_values(enum_cls: type) -> set[str]:
    return {member.value for member in enum_cls}  # type: ignore[attr-defined]


def main() -> int:
    labels = load_labels_json()
    errors: list[str] = []

    for group, enum_cls in GROUP_ENUM_MAP.items():
        group_map = cast(dict[str, str], labels.get(group) or {})
        json_keys = set(group_map.keys())
        enum_values = _enum_values(enum_cls)

        missing_in_enum = json_keys - enum_values
        missing_in_json = enum_values - json_keys

        if missing_in_enum:
            errors.append(
                f"  {group}: in labels.json but missing from {enum_cls.__name__}: "
                f"{sorted(missing_in_enum)}"
            )
        if missing_in_json:
            errors.append(
                f"  {group}: in {enum_cls.__name__} but missing from labels.json: "
                f"{sorted(missing_in_json)}"
            )

    if errors:
        print("Linear taxonomy parity FAILED:", file=sys.stderr)
        for line in errors:
            print(line, file=sys.stderr)
        print(
            "\nFix: add the missing value to BOTH labels.json AND findings_schema.py, "
            "then create the label in the Linear UI. The `linear` skill cites both "
            "sources as the single source of truth.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Taxonomy parity OK: "
        f"category={len(_enum_values(FindingCategory))}, "
        f"severity={len(_enum_values(FindingSeverity))}, "
        f"dimension={len(_enum_values(FindingDimension))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
