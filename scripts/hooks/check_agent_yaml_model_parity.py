#!/usr/bin/env python3
"""Pre-commit hook: every `scripts/agents/configs/*.yaml` must share one `model_id`,
and `shared/config.py::LLM_MODEL` must equal that majority value.

CLAUDE.md agent config table pins the default LLM model. Silent divergence
has bitten this project before (Together AI → OpenRouter migration, 2026-03-31;
the 2026-05-15 mimo-v2.5-pro incident shipped because a fleet swap touched the
YAMLs but not the Python constant), so this hook enforces parity: every
`model_id` must match the majority value, and the Python SSOT
(`shared/config.py::LLM_MODEL`) must agree with it. Divergent files are named
in the failure output; intentional per-agent overrides carry
`# HOOK-ALLOW: model-override reason=<why>`.

Runs full-tree (`pass_filenames: false`) because parity is a global property —
a single-file diff can drift the fleet without the hook seeing the reference
set.

Escape hatch:
- `# HOOK-ALLOW: model-override reason=<why>` on the YAML line (YAML comment
  syntax). Used for intentional per-agent pinning (none today). The
  `LLM_MODEL` parity check has no escape hatch — it is the SSOT.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

HOOK_ALLOW_MARKER = "HOOK-ALLOW: model-override"

EXEMPT_FILES: frozenset[str] = frozenset()

# SWI-103: registered light-model classifier slots. Each entry is a
# high-volume per-record agent that legitimately pins a lighter model
# (e.g. minimax/minimax-m2.7 for flat polarity classification). The
# `# HOOK-ALLOW: model-override reason=...` marker on the YAML
# `model_id:` line is the actual gate; this set documents the policy
# decision so reviewers can see the sanctioned slots at a glance.
LIGHT_MODEL_AGENTS: frozenset[str] = frozenset({"article_sentiment"})

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIGS_DIR = _REPO_ROOT / "scripts" / "agents" / "configs"
_CONFIG_PY = _REPO_ROOT / "scripts" / "shared" / "config.py"

_MODEL_ID_RE = re.compile(r"^model_id:\s*([^\s#]+)", re.MULTILINE)
_LLM_MODEL_LINE_RE = re.compile(r"^\s*LLM_MODEL\s*=")
_QUOTED_RE = re.compile(r"""["']([^"']+)["']""")


def _extract_config_llm_model() -> str | None:
    """Return the production `LLM_MODEL` literal from shared/config.py.

    Parses the last quoted token on the `LLM_MODEL = ...` assignment line.
    The production-tier value is a literal; the cheap-tier branch
    references a constant, so the last quoted token is the production
    model regardless of quote style or trailing comment.

    Assumption (keep it true): the PRODUCTION-tier model is the quoted
    literal and the CHEAP-tier branch references an unquoted constant. A
    symmetry refactor that quotes the cheap branch and moves production to
    a constant (`LLM_MODEL = "Qwen/..." if _tier == "cheap" else PROD`)
    would make the last quoted token the *cheap* model — silently wrong,
    not self-diagnosing. The only failure this DOES self-diagnose is the
    literal moving off a simple assignment line (caller prints guidance).
    """
    try:
        with _CONFIG_PY.open(encoding="utf-8") as config_file:
            for line in config_file:
                if _LLM_MODEL_LINE_RE.match(line):
                    quoted = _QUOTED_RE.findall(line)
                    return quoted[-1] if quoted else None
    except OSError:
        return None
    return None


def _extract_model_id(source: str) -> tuple[str | None, bool]:
    match = _MODEL_ID_RE.search(source)
    if not match:
        return None, False
    line_start = source.rfind("\n", 0, match.start()) + 1
    line_end = source.find("\n", match.start())
    if line_end == -1:
        line_end = len(source)
    line = source[line_start:line_end]
    has_allow = HOOK_ALLOW_MARKER in line
    return match.group(1).strip(), has_allow


def main() -> int:
    if not _CONFIGS_DIR.exists():
        return 0
    yaml_files = sorted(_CONFIGS_DIR.glob("*.yaml"))
    if not yaml_files:
        return 0

    results: list[tuple[str, str | None, bool]] = []
    for path in yaml_files:
        rel = f"scripts/agents/configs/{path.name}"
        if rel in EXEMPT_FILES:
            continue
        model_id, has_allow = _extract_model_id(path.read_text(encoding="utf-8"))
        results.append((rel, model_id, has_allow))

    missing = [rel for rel, model_id, _ in results if model_id is None]
    if missing:
        print("Agent configs missing `model_id`:", file=sys.stderr)
        for rel in missing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    tallied = Counter(model_id for _, model_id, allow in results if not allow and model_id)
    if not tallied:
        return 0
    expected, _ = tallied.most_common(1)[0]
    divergent = [
        (rel, model_id) for rel, model_id, allow in results if not allow and model_id != expected
    ]
    if divergent:
        print(
            "Agent YAML `model_id` drift — all configs must match the majority "
            f"(`{expected}`) unless they carry `# HOOK-ALLOW: model-override reason=...`.",
            file=sys.stderr,
        )
        for rel, model_id in divergent:
            print(f"  {rel}: model_id={model_id} (expected {expected})", file=sys.stderr)
        return 1

    config_model = _extract_config_llm_model()
    if config_model is None:
        print(
            "Could not read `LLM_MODEL` from scripts/shared/config.py — the "
            "Python SSOT must stay parseable by this hook. Keep the production "
            "value as a quoted literal on the `LLM_MODEL = ...` assignment line "
            '(e.g. `LLM_MODEL = CHEAP_MODEL if _tier == "cheap" else "<model>"`).',
            file=sys.stderr,
        )
        return 1
    if config_model != expected:
        print(
            "Model SSOT drift — scripts/shared/config.py::LLM_MODEL "
            f"(`{config_model}`) must match the YAML majority (`{expected}`). "
            "A fleet swap must update both; the 2026-05-15 incident shipped "
            "because the YAMLs moved and the Python constant did not.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
