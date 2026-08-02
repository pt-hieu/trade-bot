---
name: vnstock-api
description: Placeholder. Deployment and endpoint details are not published. Read vnstock-api/ directly for the FastAPI and SSE patterns.
---

# vnstock API — redacted

The real contents of this skill are not published. It named the live host, the
install path, the authentication header, and which routes skip the auth check.

## What the service is

A FastAPI wrapper around the [`vnstock`](https://github.com/thinh-vu/vnstock)
library, serving Vietnamese market data over HTTP with a server-sent-events
channel for live prices. The source is in `vnstock-api/`.

Read `vnstock-api/main.py` for the app setup, CORS policy, auth dependency, and
the streaming endpoints; `vnstock-api/routes_*.py` for the per-domain routes.

## Deployment

Not documented here. Note that browser `EventSource` cannot send custom headers,
so if you expose a stream to a browser you need a query-parameter token or an
edge-level access control — not an unauthenticated route.

## Library gotchas

The `vnstock` library has a premium tier with device-binding, and its data
shapes shift between versions. Pin the version and read the release notes before
upgrading.
