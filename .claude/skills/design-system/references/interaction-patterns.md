# Interaction Patterns

## Icons

- Always use lucide icons

---

## Clickable Elements

All clickable elements MUST have `cursor-pointer` class and visual cues to indicate that they are clickable.

---

## Critical Operations

Delete operations MUST show confirmation dialog. Use `<ConfirmDialog />` component.

---

## Progressive Disclosure

Dense data sections should deliver instant value at a glance. Supplementary text goes in `<DetailText>` — collapsed by default.

- Use the `DetailText` component for all expandable muted text
- Never render long interpretation paragraphs inline — always behind a toggle

---

## No Hidden Interactions

Every interactive element must have a visual cue — no discoverable-only-by-accident UX.
- Data users need to compare across rows MUST be visible columns, not tooltips
- If clickable → must look clickable (`cursor-pointer`, underline, button style)
- If expandable → show toggle/chevron/indicator
- Tooltips are ONLY for supplementary explanations (definitions) — never for data values

---

## Metric Info Icons

Use `ColumnInfo` (table headers) or `CardLabel` (card titles) for metric definitions.
- Stack: Radix `Tooltip` + `Info` icon from lucide-react (`h-3 w-3`)
- Global `TooltipProvider` in `providers.tsx` — no local wrapper needed
- Icon style: `text-muted-foreground/60 cursor-help`
- Tooltip position: `side="top"` (default)
