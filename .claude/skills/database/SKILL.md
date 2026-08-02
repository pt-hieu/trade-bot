---
name: database
description: Placeholder for the private runbook. The migration rules below are the public part. Use when creating or applying a migration.
---

# Database — partially redacted

The connection details, role names, hosting project identifiers, and network
workarounds that were in this skill are not published. The migration discipline
is, because it is the part worth copying.

## Migration rules

**Schema changes go through migrations only.** No ad-hoc DDL, ever. Migrations
live in `scripts/db/migrations/` and are numbered sequentially.

**Migrations are `.sql` files.** Not Python scripts. A migration is a
declarative statement of a schema change; putting it in a program makes it
harder to read, harder to review, and harder to replay.

**Write them idempotent.** `IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, guarded
`ALTER`. A migration that fails halfway must be safe to re-run.

**Applied migrations are recorded** in a `schema_migrations` table. The
pipelines check for drift at startup and abort if the database does not match
the migration tree.

**DDL needs a privileged role.** The connection string the pipelines use is
read-only by design. Migrations use a separate owner connection, supplied at
apply time and never committed.

There is no migration runner. Migrations are applied manually in numeric order,
and the pipeline aborts at startup if the applied set drifts from the directory.
Read `scripts/db/schema.sql` for the current shape.

## If you are running your own copy

Write your own runbook for how you connect and apply. Keep it private.
