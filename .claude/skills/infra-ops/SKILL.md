---
name: infra-ops
description: Placeholder. The operational runbook for this project's servers is not published. Use when doing infrastructure or deployment work — then supply your own runbook.
---

# Infrastructure Operations — redacted

The real contents of this skill are not published.

It documented one specific person's deployment: server addresses, SSH access
patterns, deploy paths, service names, reverse-proxy routing, memory headroom,
and the vendor accounts behind them. Publishing that is a map for attacking a
live machine, and it is worth nothing to anyone else.

## What ran here

Three services on a single small VM, behind a reverse proxy that terminates TLS:

- a FastAPI market-data service wrapping the `vnstock` library (see `vnstock-api/`)
- a read-only MCP server exposing trading data to LLM clients (see `mcp-server/`)
- an alert monitor polling for position triggers

The VM is provisioned by Terraform in `infra/`. Read those files for the shape
of the deployment; supply your own host, DNS, and credentials.

## If you are running your own copy

Write your own version of this skill. It should cover how you reach your host,
where each service is installed, how you restart them, and how you roll back.
Keep it out of version control, or keep it in a private repo.
