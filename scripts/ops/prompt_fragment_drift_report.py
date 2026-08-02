#!/usr/bin/env python3
"""Prompt fragment drift inventory.

Walks `scripts/agents/configs/*.yaml`, extracts `## HEADER` blocks from each
`system_prompt` field, groups by header name, hashes each variant body
(whitespace-normalized), and classifies every header as SHARED or PER-AGENT.

SHARED criteria (from plan D.3, convergence threshold):
  - variant_count <= 2 (the drift across consumers collapses to at most two forms)
  - consumer_count >= 4 (the block appears in enough configs to merit extraction)
  - no forbidden literal substrings in any variant body

Forbidden literals enforce the D.2 content rule — fragments must be context-free
boilerplate. These substrings flag per-agent content or injection references:
  - "YOUR PRIOR"    (belief-injection field)
  - "TICKER DATA"   (ticker-briefing header)
  - "positions_"    (agent-name reference)
  - "sector_"       (agent-name reference)
  - "longterm_"     (agent-name reference)

Usage:
    uv run python scripts/ops/prompt_fragment_drift_report.py
    uv run python scripts/ops/prompt_fragment_drift_report.py --header "TOOL RETRY GUARDRAIL"
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "agents" / "configs"
_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$")

FORBIDDEN_LITERALS: tuple[str, ...] = (
    "YOUR PRIOR",
    "TICKER DATA",
    "positions_",
    "sector_",
    "longterm_",
)

SHARED_MAX_VARIANTS = 2
SHARED_MIN_CONSUMERS = 4


@dataclass
class Block:
    header: str
    body: str  # raw lines joined with \n, leading/trailing whitespace stripped
    config_name: str

    @property
    def normalized(self) -> str:
        # Collapse runs of whitespace; strip per-line — whitespace drift should
        # not count as a new variant.
        lines = [line.strip() for line in self.body.splitlines() if line.strip()]
        return "\n".join(lines)

    @property
    def body_hash(self) -> str:
        return hashlib.sha1(self.normalized.encode()).hexdigest()[:10]


@dataclass
class HeaderReport:
    header: str
    consumers: list[str] = field(default_factory=list)
    variants: dict[str, list[Block]] = field(default_factory=dict)  # hash -> blocks

    @property
    def consumer_count(self) -> int:
        return len(self.consumers)

    @property
    def variant_count(self) -> int:
        return len(self.variants)

    def has_forbidden(self) -> tuple[bool, list[str]]:
        """Return (any_hit, sample_hits) across all variants."""
        hits: list[str] = []
        for blocks in self.variants.values():
            for literal in FORBIDDEN_LITERALS:
                if literal in blocks[0].body and literal not in hits:
                    hits.append(literal)
        return (bool(hits), hits)

    def classify(self) -> str:
        """Return "SHARED" or "PER-AGENT" with reason codes."""
        if self.variant_count > SHARED_MAX_VARIANTS:
            return f"PER-AGENT (variant_count={self.variant_count} > {SHARED_MAX_VARIANTS})"
        if self.consumer_count < SHARED_MIN_CONSUMERS:
            return f"PER-AGENT (consumer_count={self.consumer_count} < {SHARED_MIN_CONSUMERS})"
        forbidden, hits = self.has_forbidden()
        if forbidden:
            return f"PER-AGENT (forbidden literals: {', '.join(hits)})"
        return "SHARED"


def _extract_blocks(config_name: str, system_prompt: str) -> list[Block]:
    """Extract `## HEADER` blocks from a system_prompt body.

    A block starts at `## HEADER` and ends at the next `##` or at EOF. Leading
    and trailing whitespace lines are stripped from the body.
    """
    blocks: list[Block] = []
    lines = system_prompt.splitlines()
    current_header: str | None = None
    current_body: list[str] = []

    def _flush() -> None:
        if current_header is None:
            return
        body = "\n".join(current_body).strip()
        if body:
            blocks.append(Block(header=current_header, body=body, config_name=config_name))

    for line in lines:
        stripped = line.lstrip()
        match = _HEADER_RE.match(stripped)
        if match:
            _flush()
            current_header = match.group(1).strip()
            current_body = []
        elif current_header is not None:
            current_body.append(line)

    _flush()
    return blocks


def _load_configs() -> dict[str, str]:
    """Return {config_stem: system_prompt_text} for every yaml in CONFIGS_DIR."""
    result: dict[str, str] = {}
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            continue
        prompt = data.get("system_prompt")
        if isinstance(prompt, str):
            result[path.stem] = prompt
    return result


def _build_reports(configs: dict[str, str]) -> dict[str, HeaderReport]:
    """Collect all blocks from all configs into per-header reports."""
    reports: dict[str, HeaderReport] = {}
    for config_name, prompt in configs.items():
        blocks = _extract_blocks(config_name, prompt)
        for block in blocks:
            report = reports.setdefault(block.header, HeaderReport(header=block.header))
            if config_name not in report.consumers:
                report.consumers.append(config_name)
            report.variants.setdefault(block.body_hash, []).append(block)
    return reports


def _print_report(reports: dict[str, HeaderReport], filter_header: str | None) -> None:
    shared: list[HeaderReport] = []
    per_agent: list[HeaderReport] = []
    for report in reports.values():
        if filter_header and report.header != filter_header:
            continue
        (shared if report.classify() == "SHARED" else per_agent).append(report)

    shared.sort(key=lambda r: (-r.consumer_count, r.header))
    per_agent.sort(key=lambda r: (-r.consumer_count, r.header))

    print("=" * 72)
    print(f"PROMPT FRAGMENT DRIFT REPORT — {len(reports)} distinct headers")
    print(
        f"SHARED={len(shared)}  PER-AGENT={len(per_agent)}  "
        f"thresholds: variants<={SHARED_MAX_VARIANTS} consumers>={SHARED_MIN_CONSUMERS}"
    )
    print("=" * 72)

    if shared:
        print("\n## SHARED fragments (candidates for extraction)\n")
        for report in shared:
            _print_header_detail(report, verbose=True)

    if per_agent:
        print("\n## PER-AGENT blocks (excluded from extraction)\n")
        for report in per_agent:
            _print_header_detail(report, verbose=bool(filter_header))


def _print_header_detail(report: HeaderReport, *, verbose: bool) -> None:
    print(f"- {report.header!r}")
    print(
        f"    consumers={report.consumer_count}  "
        f"variants={report.variant_count}  "
        f"classification: {report.classify()}"
    )
    if verbose:
        for idx, (body_hash, blocks) in enumerate(
            sorted(report.variants.items(), key=lambda kv: -len(kv[1])),
            start=1,
        ):
            names = sorted(block.config_name for block in blocks)
            print(f"    variant {idx} (hash {body_hash}, {len(blocks)} configs): {names}")
            sample = blocks[0].body
            preview = sample if len(sample) < 600 else sample[:600] + " ..."
            for line in preview.splitlines():
                print(f"        {line}")
            print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--header",
        help="Only inspect a single header name (verbose output for it).",
    )
    args = parser.parse_args()

    configs = _load_configs()
    if not configs:
        print(f"No yaml configs found under {CONFIGS_DIR}", file=sys.stderr)
        return 1

    reports = _build_reports(configs)
    _print_report(reports, filter_header=args.header)
    return 0


if __name__ == "__main__":
    sys.exit(main())
