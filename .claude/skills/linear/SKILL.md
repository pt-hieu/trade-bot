---
name: linear
description: Placeholder. The issue-tracker protocol for this project is not published. Use when you want the idea, not the implementation.
---

# Linear — redacted

The real contents of this skill are not published. It encoded one person's
private Linear workspace: team identifier, label and workflow-state object ids,
filing recipes, and routing rules that referenced a personal notes store.

## The idea, which is the transferable part

A solo project developed on `main` with no pull requests has no natural place to
record *why*. Commit messages carry the what. Everything else — a bug found and
deferred, a regression being watched, an architectural fork chosen and the
option rejected, an audit finding not yet acted on — evaporates between
sessions.

The fix is an issue tracker used as long-horizon memory rather than as a task
list. Two rules make it work:

1. **Every commit subject references an issue id.** `git log --grep=<id>` then
   reconstructs the full history of any decision.
2. **File anything with cross-session value**, including things you are not
   going to do. A deferred decision with its trigger written down is worth more
   than a clean backlog.

Paired with git history, that is the only context that survives.

## If you are running your own copy

Use whatever tracker you like. Write your own version of this skill with your
own identifiers, and keep it private — object ids and a label census are not
useful to anyone else.
