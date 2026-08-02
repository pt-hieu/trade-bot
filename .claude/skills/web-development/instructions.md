# Web Development

## Stack Decisions

| Technology | Why |
|-----------|-----|
| TanStack Start | Full-stack React framework, SSR, server functions, file-based routing |
| Cloudflare Workers | Edge deployment, $5/mo, free bandwidth, global CDN |
| React 19 | Latest concurrent features |
| TanStack Query v5 | Server state management: caching, invalidation, loading/error states |
| TanStack Router | Type-safe file-based routing, search params, loaders |
| Radix UI | Accessible headless primitives (Dialog, Dropdown, Select, Tabs) |
| Tailwind CSS 4 | Utility-first, dark mode by default, Vite plugin |
| Vite | Dev server + build tool, replaces Next.js Turbopack |

**Dev commands:**
- `pnpm dev` — start dev server on port 3000 (Vite + CF Workers runtime)
- `pnpm build` — production build
- `pnpm deploy` — build + deploy to Cloudflare Workers
- `pnpm tsc --noEmit` — type check without building

**Required env vars** (in `web/.env`):
- `DATABASE_URL` — Neon serverless connection string
- `VNSTOCK_API_URL` — vnstock-api server URL (server-side)
- `VITE_VNSTOCK_API_URL` — vnstock-api URL (client-side, for SSE streaming)
- `TOGETHER_AI_API_KEY` — Together AI for chat

---

## Project Structure

```
web/
├── src/
│   ├── routes/           # File-based routing (TanStack Router)
│   │   ├── __root.tsx    # Root layout (Nav, ChatPanel, Providers)
│   │   ├── index.tsx     # Home/War Room
│   │   ├── *.tsx         # Page routes
│   │   ├── intel/        # Nested layout routes
│   │   └── api/chat.ts   # Chat streaming server route
│   ├── server/
│   │   ├── db.ts         # Neon connection (getSql)
│   │   ├── vnstock.ts    # vnstock API helpers
│   │   ├── trading-config.ts
│   │   ├── goal-sync.ts
│   │   ├── queries/      # Shared SQL fragments
│   │   └── fns/          # Server functions (createServerFn)
│   ├── hooks/            # TanStack Query hooks (call server fns directly)
│   ├── components/       # UI components
│   ├── lib/              # Client-safe utils, date, chat system
│   └── types/            # TypeScript types
├── vite.config.ts        # Vite + Cloudflare + TanStack Start + Tailwind
├── wrangler.jsonc        # Cloudflare Workers config
└── tsconfig.json
```

---

## Data Fetching Philosophy

All server data flows through TanStack Query hooks → server functions → Neon.

- **Server functions** in `src/server/fns/*.ts` replace Next.js API routes
- **Hooks** in `src/hooks/use-*.ts` call server functions directly (no fetch wrapper)
- **No `api.ts` fetch layer** — server functions are called as regular functions
- Default `staleTime: 60_000` (1 min) prevents redundant refetches

```typescript
// Server function (src/server/fns/portfolio.ts)
export const getPortfolio = createServerFn({ method: 'GET' }).handler(async () => {
  const sql = getSql()
  return await sql`SELECT * FROM v_portfolio_current`
})

// Hook (src/hooks/use-portfolio.ts)
export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => getPortfolio(),
  })
}
```

---

## Server Functions

Replace Next.js API routes. Three patterns:

```typescript
// Read-only, no params
export const getPortfolio = createServerFn({ method: 'GET' })
  .handler(async () => { ... })

// Read with params
export const getWatchlist = createServerFn({ method: 'GET' })
  .inputValidator((data: { type: string }) => data)
  .handler(async ({ data }) => { ... })

// Mutation
export const createTrade = createServerFn({ method: 'POST' })
  .inputValidator((data: TradeInput) => data)
  .handler(async ({ data }) => { ... })
```

---

## Routing

File-based routing via TanStack Router in `src/routes/`.

- `__root.tsx` — root layout with `shellComponent` + `component`
- `index.tsx` — home page at `/`
- `portfolio.tsx` — page at `/portfolio`
- `intel/route.tsx` — nested layout for `/intel/*`
- `intel/index.tsx` — page at `/intel`
- `api/chat.ts` — server route with `server.handlers.POST`
- All pages use `ssr: false` — client-rendered, data via TanStack Query

---

## CRITICAL: Import Rules

**Use RELATIVE imports only.** The `@/` alias does NOT resolve in Cloudflare Workers SSR environment.

```typescript
// ✅ CORRECT
import { getSql } from '../db'
import { Nav } from '../components/nav'

// ❌ WRONG — breaks in CF Workers SSR
import { getSql } from '@/server/db'
import { Nav } from '@/components/nav'
```

---

## Anti-Patterns

- **NEVER use `@/` imports** — CF Workers SSR doesn't resolve tsconfig paths
- **NEVER run `pnpm build` during development** — erases dev assets
- **NEVER access `process.env` at module level** — read lazily inside functions
- Never put server-side DB logic in client components
- Never create local duplicates of formatters — use `../lib/utils`
- Never store derived values as state — compute with `useMemo`

---

---

## Gotchas

- **Server fn calling server fn hangs Workers**: `createServerFn` handlers cannot call other `createServerFn` functions — the Workers runtime detects a hang and kills the request. Extract shared logic into plain `async` functions (e.g., `fetchEnhancedHoldings`) and have both the server fn and internal callers use that. If the caller already has a `getSql()` instance, pass it through to avoid creating a second Neon connection.
- **Concurrent outbound fetches in Promise.all**: Miniflare (CF Workers dev runtime) can hang when too many concurrent outbound HTTP requests fire from a single handler. Keep `Promise.all` to ≤4 concurrent Neon queries. Run additional queries sequentially after the batch.
- **`v_portfolio_current` is per-position, not per-ticker**: The view sources from `portfolio_holdings` which stores individual lots. JOINing it to `trades_calculated` on ticker alone creates a cross product (N holdings × M trades). Use `trades_calculated` as primary source for trade-level views, join per-ticker data (price, sector) via a `DISTINCT ON (ticker)` CTE.
- **`pl_pct` in `trades_calculated` is already percentage**: A value of `12.5` means 12.5%. Do NOT multiply by 100 again in SQL queries.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `design-system` | Styling components, using enum display values, applying empty/error/loading states |
| `data-layer` | Understanding where server function SQL queries get their data from |
| `vnstock-api` | Debugging SSE stream issues or adding new stream event types |
| `coordinator-architecture` | Modifying the chat coordinator, tool broker, or sub-agent routing in `web/lib/chat/` |
