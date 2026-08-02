# Frontend Design System Reference

All rules are split into reference files. Read the ones relevant to your task.

| File | Contents |
|------|----------|
| [enums-formatting.md](references/enums-formatting.md) | DB enum values, TypeScript type rules, data formatters, date format, text casing, sector names |
| [component-states.md](references/component-states.md) | Empty states, error states, loading states (skeletons, spinners) |
| [interaction-patterns.md](references/interaction-patterns.md) | Icons, clickable elements, critical operations, progressive disclosure, hidden interactions, metric info icons |
| [banned-patterns.md](references/banned-patterns.md) | Accent bars, arbitrary font sizes, text opacity modifiers, chevron placement |
| [design-principles.md](references/design-principles.md) | 15 non-negotiable design principles (hierarchy, scanning, escalation, dedup, etc.) |
| [drawer-dialog.md](references/drawer-dialog.md) | Drawer vs dialog: when to use each, sizing, content budgets, chaining pattern |

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `web-development` | Building the component structure, hooks, or API routes that the UI renders |
| `database` | Enum management and schema source of truth — check `scripts/db/schema.sql` for exact PostgreSQL enum values before defining TypeScript types |
