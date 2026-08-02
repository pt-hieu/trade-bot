# Component States

## Empty States

Never show blank/nothing — always explain WHY it's empty + what action populates it.

**Large sections** (full page, main content area):
- SVG illustration + title + description + CTA button(s)
- Illustration style: muted strokes, subtle gradients — match dark theme, no cartoon/clipart
- Pass `illustration` prop (ReactNode) to `<EmptyState />`

**Small areas** (table bodies, card content):
- Lucide icon + text + optional inline CTA — no illustration
- Pass `icon` prop (LucideIcon) to `<EmptyState />`

- Description must be actionable: "No trades recorded yet" → "Record your first trade to start tracking performance"
- CTA buttons use primary variant for the main action
- For pipeline-dependent data, include timing context: "runs at 7 AM on trading days"

---

## Error States

All data-fetching components MUST handle errors — never silently hide failures.

Always pass `retry={refetch}` so users can retry. For dashboard sections with headers, wrap ErrorState inside section layout to preserve heading.

---

## Loading States

All async operations MUST have visual loading feedback.

**Mutations (POST/PUT/DELETE):**
- `<Spinner />` inside button + button `disabled` + loading text ("Saving...")

**Queries (GET):**
- Skeleton placeholders matching real layout shape (same heights, widths, gaps, padding)
- NEVER show bare spinner for page-level query loading — always skeletons
