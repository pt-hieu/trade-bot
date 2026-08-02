# Drawer vs Dialog

## Drawer — Detail Without Losing Context

The drawer is a parallel reading pane, not a navigation event. The parent list stays visible and interactive; clicking a different item swaps drawer content with no close/reopen cycle. Closing preserves scroll position. Mental model: "I'm still on the same page, looking at one thing more closely."

**When to use:** The page has a scannable list of entities (holdings, zones, picks, tickers, alerts, trades) and the user needs to drill into one while keeping others visible for comparison. The list is the anchor. The drawer is the lens.

**When NOT to use:**
- Content has no parent list (standalone summaries, regime banners)
- Items the system told you to ignore (skip list) — a drawer gives too much ceremony to low-priority content
- Detail is so heavy it needs its own page (full research reports, multi-section analysis with charts)

**Content budget:** Scannable in one glance on open — no scrolling required. Default shows only Tier 2 content: verdict, visual score indicators, key numbers, action/status. Deeper analysis lives behind a toggle ("Full analysis") as Tier 3 expansion. **Rule: if the default drawer content requires scrolling, you've put too much in it.** Compress, tier it, or reconsider the container.

**Sizing:**
- Narrow (~350px) — simple stat lookups
- Medium (~450px) — structured summaries with scores and short prose
- Wide (~550-600px) — metrics tables or side-by-side comparisons
- **Never wider than 50% of viewport** — parent list must remain usable

**Transitions:** Opening compresses main content — doesn't overlay it. Parent list must remain visible. On mobile, use a bottom sheet instead with clear "back to list" gesture.

---

## Dialog — Focused Action, Then Return

The dialog is a decision checkpoint. It appears when the user commits to something consequential — execute a trade, confirm an exit, set an alert. It demands a response (confirm, cancel, modify) and disappears. Mental model: "I've been pulled aside to make a call, then I'm back."

**When to use:**
- Action is irreversible or consequential (placing orders, exiting positions, canceling alerts, modifying stops)
- Action needs user-supplied input that doesn't belong in the main page flow (limit price, position size, notes)
- Confirming something the system will do on the user's behalf

**When NOT to use:**
- Reading or inspecting data — that's a drawer
- Low-stakes toggles (switching filters, toggling insights) — those are inline
- Content that benefits from comparison with parent page — dialog blocks the page, drawer doesn't
- User needs to reference the list while filling out the form — use a drawer with a form inside

**Content budget:** Completable in one action. **Rule: if the dialog requires scrolling, tabs, or multi-step navigation, it's too heavy.** Ideal dialog: context line (what you're acting on) + input fields (what you're deciding) + two buttons (confirm/cancel). Max 3-5 input fields. No embedded tables or lists. If user needs to read extensively before acting → drawer with CTA. If more than one screen of fields → dedicated form page.

**Sizing:**
- Small (~400px) — confirmations with no input ("Exit FPT at market?")
- Medium (~500px) — actions with a few fields (ticker, price, quantity, stop)
- **Never full-width** — dimmed background reminds user this is a temporary interruption

---

## The Boundary

| Interaction starts with... | Container |
|----------------------------|-----------|
| "Let me look at this" | Drawer |
| "Let me do something" | Dialog |
| "Let me look, then maybe act" | Drawer → CTA button → Dialog |

Core interaction loop: **list → drawer (inspect) → dialog (act) → back to list**.

The drawer is for reading. The dialog is for deciding. A drawer keeps you in context while you inspect. A dialog interrupts context because the action deserves full attention. They chain naturally: scan list → open drawer → click CTA → dialog confirms → back to list.
