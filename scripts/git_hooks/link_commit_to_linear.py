#!/usr/bin/env python3
"""post-commit hook: post `shipped in <sha>` to every SWI-NN named in the
commit subject, and drive each SWI to the appropriate close state:

* ``regression-watch`` items → ``Resolved Candidate`` (soak window;
  ``auto_promote.py`` flips to Resolved after clean trading days).
* All other categories (scheduled-work, audit-finding, quality-gap, bug,
  feature, etc.) → ``Resolved`` directly.

Closes the bidirectional graph from the commit side (`git log --grep=SWI-NN`
plus the SWI's `shipped in <sha>` comment) and removes the manual
"flip-after-ship" step that left SWI-66 / SWI-67 / SWI-159 stale in Deferred
for days after the code shipped. Develop-on-main workflow assumes every
commit referencing a SWI IS the closing commit; partial-fix commits should
omit the SWI prefix or reopen the ticket manually post-flip.

Already-terminal states (``Resolved Candidate``, ``Resolved``, ``Superseded``)
are skipped so the hook never re-flips a soaking ticket back out of
candidate, never re-opens a closed ticket, and never wakes a superseded one.

Fail-soft: never blocks the commit. Network/API failures log to
`scripts/linear_migration/processed_reports/post_commit_failures.log` so the
developer can re-link on a quiet network.

Triggered by:
  $ git config --local --get core.hooksPath  # repo-local hooks dir
or wired through pre-commit's `[post-commit]` stage.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SWI_RE = re.compile(r"\bSWI-(\d+)\b")
FAILURE_LOG = (
    _REPO_ROOT / "scripts" / "linear_migration" / "processed_reports" / "post_commit_failures.log"
)

# Terminal/soaking states the hook MUST NOT touch:
# - Resolved Candidate: actively soaking under auto_promote's invariants;
#   re-flipping would reset the clean-run counter.
# - Resolved: already closed.
# - Superseded: cancelled, must not be re-opened.
_TERMINAL_STATES = {"Resolved Candidate", "Resolved", "Superseded"}
_REGRESSION_WATCH_LABEL = "regression-watch"


def _target_state_for(labels: list[str]) -> str:
    """Pick the close state from the issue's category labels.

    ``regression-watch`` carries an implicit soak requirement (a regression
    might re-trigger after the fix), so those items park at ``Resolved
    Candidate`` for ``auto_promote.py`` to confirm. Everything else is a
    one-shot ship → ``Resolved`` immediately.
    """
    if _REGRESSION_WATCH_LABEL in labels:
        return "Resolved Candidate"
    return "Resolved"


def _commit_metadata() -> tuple[str, str]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return sha, subject


def _log_failure(sha: str, swi_id: str, reason: str) -> None:
    FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with FAILURE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp}\t{swi_id}\t{sha[:12]}\t{reason}\n")


def _resolve_uuid_state_labels(client, swi_id: str) -> tuple[str | None, str | None, list[str]]:
    """Single GraphQL roundtrip for the issue's UUID + state name + label names."""
    data = client.query(
        """
        query($id: String!) {
          issue(id: $id) {
            id
            state { name }
            labels { nodes { name } }
          }
        }
        """,
        {"id": swi_id},
    )
    issue = cast(dict[str, object], data.get("issue") or {})
    state_obj = cast(dict[str, object], issue.get("state") or {})
    labels_obj = cast(dict[str, object], issue.get("labels") or {})
    label_nodes = cast(list[dict[str, object]], labels_obj.get("nodes") or [])
    label_names = [cast(str, n.get("name")) for n in label_nodes if n.get("name")]
    return (
        cast(str | None, issue.get("id")),
        cast(str | None, state_obj.get("name")),
        label_names,
    )


def _handle_swi(
    client,
    state_ids: dict[str, str],
    swi_id: str,
    sha: str,
    subject: str,
) -> tuple[bool, bool, str, str]:
    """Post `shipped in <sha>` AND drive non-terminal states to the proper
    close state (``Resolved`` or ``Resolved Candidate`` for regression-watch).
    Returns ``(comment_ok, transitioned, target_state, reason)`` — fail-soft.
    """
    from scripts.linear_migration.tag_actions import post_comment, set_state

    try:
        linear_uuid, state_name, label_names = _resolve_uuid_state_labels(client, swi_id)
        if not linear_uuid:
            return False, False, "", f"could not resolve {swi_id}"
        post_comment(client, linear_uuid, f"shipped in {sha[:12]} — `{subject}`")

        if state_name in _TERMINAL_STATES:
            return True, False, "", ""
        target_state = _target_state_for(label_names)
        target_id = state_ids.get(target_state)
        if not target_id:
            return True, False, "", f"state '{target_state}' missing in team states"
        set_state(client, linear_uuid, target_id)
        return True, True, target_state, ""
    except Exception as exc:  # noqa: BLE001 — fail-soft
        return False, False, "", f"{type(exc).__name__}: {exc}"


def _connect_and_handle(
    swi_numbers: list[str], sha: str, subject: str
) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Open one Linear client, fetch state ids once, fan out across SWIs."""
    try:
        from scripts.linear_migration.client import (
            LinearClient,
            load_team_id,
            state_ids_by_name,
        )
    except Exception as exc:  # pragma: no cover — import fail is fail-soft
        reason = f"import failure: {exc}"
        return [f"{f'SWI-{n}'}: {reason}" for n in swi_numbers], [], []

    # Load .env directly via dotenv (cannot import `scripts.shared.env`
    # without triggering scripts.shared.__init__'s heavy transitive imports).
    # Both files are loaded so the hook works regardless of SWINGY_ENV — the
    # secret only needs to live in one of them.
    try:
        from dotenv import load_dotenv

        for env_file in (_REPO_ROOT / ".env.local", _REPO_ROOT / ".env"):
            if env_file.exists():
                load_dotenv(env_file, override=False)
    except Exception:  # noqa: BLE001 — env-load is best-effort; the hook is fail-soft
        pass

    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        return [f"SWI-{n}: LINEAR_API_KEY missing" for n in swi_numbers], [], []

    failures: list[str] = []
    transitioned_ids: list[tuple[str, str]] = []
    transition_warnings: list[str] = []
    try:
        with LinearClient(api_key) as client:
            try:
                state_ids = state_ids_by_name(client, load_team_id())
            except Exception as exc:  # noqa: BLE001 — degrade to comment-only
                state_ids = {}
                transition_warnings.append(
                    f"state-id fetch failed; transitions skipped: {type(exc).__name__}: {exc}"
                )
            for n in swi_numbers:
                swi_id = f"SWI-{n}"
                comment_ok, transitioned, target_state, reason = _handle_swi(
                    client, state_ids, swi_id, sha, subject
                )
                if not comment_ok:
                    _log_failure(sha, swi_id, reason)
                    failures.append(f"{swi_id}: {reason}")
                    continue
                if transitioned:
                    transitioned_ids.append((swi_id, target_state))
                elif reason:
                    _log_failure(sha, swi_id, reason)
                    transition_warnings.append(f"{swi_id}: {reason}")
    except Exception as exc:  # noqa: BLE001 — fail-soft, log every SWI
        reason = f"{type(exc).__name__}: {exc}"
        for n in swi_numbers:
            swi_id = f"SWI-{n}"
            _log_failure(sha, swi_id, reason)
            failures.append(f"{swi_id}: {reason}")
    return failures, transitioned_ids, transition_warnings


def main() -> int:
    if os.environ.get("SWINGY_SKIP_POST_COMMIT_LINEAR") == "1":
        return 0
    try:
        sha, subject = _commit_metadata()
    except subprocess.CalledProcessError:
        return 0

    swi_numbers = sorted(set(SWI_RE.findall(subject)))
    if not swi_numbers:
        return 0

    failures, transitioned_ids, transition_warnings = _connect_and_handle(swi_numbers, sha, subject)

    if failures:
        print(
            "[linear skill] post-commit linker partially failed (logged); commit succeeded.",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
    else:
        linked = ", ".join(f"SWI-{n}" for n in swi_numbers)
        if transitioned_ids:
            moves = ", ".join(f"{sid} → {state}" for sid, state in transitioned_ids)
            moved = f" ({moves})"
        else:
            moved = ""
        print(f"[linear skill] linked {sha[:12]} → {linked}{moved}", file=sys.stderr)
    for warning in transition_warnings:
        print(f"[linear skill] {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
