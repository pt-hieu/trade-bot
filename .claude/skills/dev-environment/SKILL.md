---
name: dev-environment
description: Placeholder. Machine-specific setup notes are not published. Use when setting up locally — see README.md for the supported path.
---

# Development Environment — redacted

The real contents of this skill are not published.

It described one person's machine: their operating system, package manager
paths, home internet provider and how it interfered with the database
connection, which network to switch to when that happened, and the names of
every secret in their environment. That is a fingerprint of an individual, not
setup documentation.

## Setup

`README.md` covers the supported path: Python 3.12+, `uv`, and PostgreSQL.

```bash
uv sync
docker compose up -d
psql "$DATABASE_URL" -f scripts/db/schema.sql
for f in scripts/db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
SWINGY_DRY_RUN=1 uv run python scripts/daily_scan.py
```

Start with `SWINGY_DRY_RUN=1`. It exercises the full pipeline and writes nothing.

## Configuration

Every credential is read from the environment. `README.md` lists the variables
the code expects. `web/.env.example` and `infra/terraform.tfvars.example` show
the shape of each value.

## If you are running your own copy

Write your own version of this skill for anything specific to your machine, and
keep it out of version control.
