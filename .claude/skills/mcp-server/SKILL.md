---
name: mcp-server
description: Placeholder. Deployment details for the MCP server are not published. Read mcp-server/ directly for the tool registration pattern.
---

# MCP Server — redacted

The real contents of this skill are not published. It documented where this
service is installed, how it is restarted, and the conditions under which it
serves requests without authentication. That last part is an invitation.

## What the service is

A read-only [FastMCP](https://github.com/jlowin/fastmcp) server exposing trading
data to LLM clients. The source is in `mcp-server/`. Tools are registered per
data domain and every one of them reads; none writes.

Read `mcp-server/server.py` for the lifespan, transport, and auth setup, and
`mcp-server/tools/` for the registration pattern.

## Deployment

Not documented here. Bind it to localhost, put your own reverse proxy in front,
and require a token. If your token environment variable is unset, the server
should refuse to start rather than serve openly.
