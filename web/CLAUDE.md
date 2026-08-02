# Swingy Web — Development Rules

## Stack

TanStack Start + Cloudflare Workers + TanStack Query v5 + Radix UI + Tailwind CSS 4

## Verification

**NEVER run `pnpm build` if `pnpm dev` is running.** Dev server on port 3000 — build erases dev assets.

- `pnpm tsc --noEmit` — type-check
- `pnpm dev` — start dev server (Vite + CF Workers runtime)
- `pnpm build` — production build
- `pnpm run deploy` — build + wrangler deploy to Cloudflare Workers

## Key Conventions

- **RELATIVE imports only** — `@/` alias doesn't resolve in CF Workers SSR. Always use `../` relative paths.
- **`ssr: false`** on all page routes — app is client-rendered, server functions handle data
- **Server functions** in `src/server/fns/*.ts` — use `createServerFn({ method }).inputValidator().handler()`
- **No `process.env` at module level** — lazy read inside functions for CF Workers compatibility
- **`wrangler.jsonc`** for CF Workers config, NOT `wrangler.toml`

## Design Principles

1. **One visual language** — shared skeleton across cards, strips, panels. Differentiate with color/span, not different anatomy.
2. **Hierarchy is the product** — user knows where to look in 2 seconds without reading. High-importance = visual dominance.
3. **Show relationships** — cross-link via shared keys (tickers, dates). Connected items discoverable on click, not just co-located.
4. **Match interaction to usage** — side panels for scan-and-click workflows, modals only for confirmation. Preserve feed context.
5. **Earn visual weight** — every tag/badge/dot must do scannable work. No legend = noise. Fewer meaningful signals > many ambiguous ones.
6. **Progressive disclosure by importance** — high-value items get real estate (2-col span), low-value compress (1-col compact).
7. **Design entry point first** — top of page = "what matters now." Most polished, most scannable component.
8. **Consistency = trust** — same spacing, padding, font sizes, card anatomy everywhere. Unintentional variation confuses.
9. **Design for scanning** — scores as bars not just numbers, types as color/width not just labels, sentiment as tint not just hover.
10. **Data carries its verdict** — color/style values based on whether they're good or bad in context. Never display neutrally when the system knows the interpretation.
11. **Group by decision entity** — triage UIs group by what you act on (ticker), not what generated the data (pipeline run, date). Collapse repeats and surface the count as a signal. Grouping should generate insight, not just save space.
12. **Escalation proportional to severity** — entire page shape changes with severity, not just the banner. Tiers across banners, containers, and content opacity. Same page at 2 and 34 is lying.
13. **Stale data loses visual weight** — when conditions are no longer met or data has aged, dim the entire container (opacity-50). Dead items at full opacity compete with live ones.
14. **Every drill-down needs a CTA** — expanding for context without an action = dead-end. CTA scoped to the expanded content, not generic page-level.
15. **Deduplication is intelligence** — don't just hide duplicates, surface why they repeated. Repeat count, source diversity, temporal pattern = new information from the grouping itself.

## On-Demand Skills

- `front-design:frontend-design` - always use
- `web-development` — stack, project structure, server functions, data fetching, TypeScript types, dev commands
- `design-system` — UI rules, database enum mappings, empty/error/loading states, formatters, component patterns
- `ai-sdk` — for everything related to Vercel AI SDK package
