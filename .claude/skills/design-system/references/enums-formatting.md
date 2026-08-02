# Enums & Data Formatting

## Database Enum Values

**CRITICAL:** TypeScript enum/union values MUST match PostgreSQL enum values exactly (case-sensitive).

| Table | Column | PostgreSQL Enum Values |
|-------|--------|------------------------|
| `goals` | `status` | `'Active'`, `'Achieved'`, `'Failed'`, `'Paused'` |
| `goals` | `goal_type` | `'Monthly'`, `'Quarterly'`, `'Yearly'`, `'Custom'` |
| `trades_calculated` | `status` | `'OPEN'`, `'CLOSED'`, `'CANCELLED'`, `'PARTIAL'` |
| `trades_calculated` | `strategy` | `'Bounce'`, `'Trend'`, `'Breakout'`, `'Divergence'` |
| `trades_calculated` | `plan_type` | `'SWING'`, `'LONGTERM'` |
| `longterm_watchlist` | `conviction` | `'High'`, `'Medium-High'`, `'Medium'`, `'Medium-Low'`, `'Low'` |

### Enum Rules
1. **Never transform enum values** in API routes (no `toLowerCase()`, `toUpperCase()`)
2. **Define TypeScript types** with exact DB enum values
3. **Use exact values** in form defaults and constants
4. When adding new enums, check `scripts/db/schema.sql` for exact values

---

## Data Formatting

All formatters live in `web/lib/utils` — never create local duplicates in components.
All formatters are null-safe — return `'—'` for null/undefined/NaN.

| Function | Output Example |
|----------|----------------|
| `formatVND(amount)` | `26.600.000 ₫` |
| `formatPct(pct)` | `+1.50%` or `-3.14%` |
| `formatCompact(value)` | `1.5B`, `26.6M`, `5K` |
| `cn(...inputs)` | Tailwind class merge |

---

## Date Format

- Display dates as `DD MMM YYYY` (e.g., "02 Feb 2026")
- `toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })`

---

## Text Casing

- **No ALL CAPS** — never use `uppercase` or `tracking-wide` in copy, except card/section titles
- **Labels and navigation** — always sentence case
- **Chips/badges** — Title Case (e.g., "Risk On", "Near Entry", "Buy Zone")
- **Enum display** — transform DB enums to Title Case (`RISK_ON` → "Risk On", `NEAR_ENTRY` → "Near Entry")

---

## Sector Names

- DB stores snake_case (`real_estate`, `state_owned`)
- Display: `.replace(/_/g, ' ')` + capitalize each word
