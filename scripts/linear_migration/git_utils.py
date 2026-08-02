"""Shared git subprocess helpers for the Linear stack.

Single source for "does this sha exist AND does its subject name this SWI?" —
the same question is asked from three call sites (auto-promote Invariant 3,
the reconciler's resolved-candidate-close rule, and the future closing-commit
detector). Single subprocess: ``git log -1 --pretty=%s <sha>`` exits non-zero
on missing shas, so the cat-file pre-check is redundant.
"""

from __future__ import annotations

import subprocess


def commit_subject_references(commit_sha: str, swi_handle: str, *, timeout: int = 5) -> bool:
    """Return True when ``commit_sha`` is a real commit AND its subject names
    ``swi_handle`` (e.g. ``SWI-42``).

    One subprocess call. Empty inputs return False without invoking git.
    """
    if not commit_sha or not swi_handle:
        return False
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s", commit_sha],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return swi_handle in result.stdout


def commits_grep_since(swi_handle: str, since_iso: str, *, timeout: int = 15) -> bool:
    """Return True when any commit reachable from ``HEAD`` newer than
    ``since_iso`` names ``swi_handle`` in its subject. Soft "developer is
    working on it" signal for the reconciler's silence rule.
    """
    if not swi_handle or not since_iso:
        return False
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={since_iso}",
                f"--grep=\\b{swi_handle}\\b",
                "--pretty=%H",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return bool(result.stdout.strip())
