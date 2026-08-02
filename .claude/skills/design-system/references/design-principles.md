# Design Principles

Non-negotiable rules governing all UI design decisions.

### 1. One Visual Language, Everywhere
Every element on a page must feel like it came from the same system. Cards, strips, panels, and dialogs share the same skeleton — differentiate with subtle signals (color labels, column spans, tints), not different anatomy. If two things look structurally different, users assume they ARE different.

### 2. Hierarchy Is the Product
When everything screams at the same volume, nothing communicates. Pick what matters most and give it visual dominance — size, position, color intensity. Everything else gets progressively quieter. The user should know where to look in the first 2 seconds without reading anything.

### 3. Show Relationships, Not Just Data
Two parallel lists with shared tickers is data. Clicking a theme and seeing connected catalysts appear is intelligence. Always ask: "how does this item relate to other items, and can the user discover that?" Cross-link via shared keys (tickers, dates, categories). The value is in the connections.

### 4. Match Interaction Model to Usage Pattern
Modals force context switches — use side panels to preserve context when users scan and click through items. Match the UI mechanic to how people actually work, not to what's easiest to implement.

### 5. Earn Your Visual Weight
Every element — tags, badges, scores, dots — must do clear, scannable work. A colored dot with no legend is visual noise. Five tags on one card where you can't distinguish categories from maturity from momentum hurts more than helps. Fewer, more meaningful signals beat more, ambiguous ones.

### 6. Progressive Disclosure by Importance
High-value items get real estate (2-column span, full card). Low-value items compress (single column, compact). This tells the user "pay attention here, skim there" through layout alone, without reading scores.

### 7. Design the Entry Point First
The top of the page answers "what matters right now." If the spotlight/summary strip is the least designed element, the hierarchy is inverted. The first thing users see should be the most polished, most scannable component.

### 8. Consistency Creates Trust
Same spacing, same padding, same font sizes, same card anatomy across the entire page. Unintentional visual variation makes users question whether they're looking at the same type of data or something new. Strict 8px grid system for spacing.

### 9. Design for Scanning, Not Reading
If a user has to read the UI to understand it, the design isn't done. Scores: bars, not just numbers. Types: color/width/position, not just labels. Sentiment: tint/icon, not just hover. Design for peripheral vision first, focused reading second.

### 10. Data Carries Its Verdict
Never display a value neutrally when the system knows whether it's good or bad. "now 68,000" next to "Price Below 65,000" should be red/struck — the condition is no longer met. Green if still met. The user shouldn't have to do the comparison mentally. Color and style encode the interpretation, not just the number.

### 11. Group by Decision Entity, Not by Event
Triage UIs group by the thing you act on (ticker, customer, issue), not the event that generated the data (morning brief, pipeline run, date). 34 alerts for 6 tickers = 6 collapsible rows, not 34 cards. The event is context inside the group, not the grouping axis. When the same entity repeats, collapse — don't repeat — and surface the repeat count as a signal, not just a compression artifact. Grouping should generate insight ("4x this week"), not just save space.

### 12. Escalation Proportional to Severity
The entire page shape should change with severity, not just the status bar. Define tiers (info → warning → alarm) across all visual layers — banners, containers, and content opacity. 2 triggered alerts ≠ 34 triggered alerts. High counts change banner shape (escalation rows, bulk actions, named callouts), dead items dim their containers, live items stay bright. A page that looks the same at 2 and 34 is lying about urgency.

### 13. Stale Data Loses Visual Weight
When a condition is no longer met, data has aged past relevance, or an item has been superseded — dim the entire container (opacity-50/60), not just annotate the staleness with a label. Dead items occupying prime real estate at full opacity compete with live items for attention. Visual weight must track liveness.

### 14. Every Drill-Down Needs a CTA
Expanding a row or section for context without offering an action creates a dead-end triage loop: scan → expand → learn → close → go elsewhere to act. Every expanded section needs at minimum one primary action (dismiss, act, snooze) anchored visibly to the scope of the expanded content, not a generic page-level action. "Dismiss duplicates" scoped to the expanded group > a generic "Dismiss" button. Information without a next step is a cul-de-sac.

### 15. Deduplication Is Intelligence, Not Compression
When you detect duplicates, don't just hide them — surface why they repeated and whether the repetition itself is meaningful. "Same signal across 4 briefs" tells the user something they couldn't see before. "Multi-source" (Morning Brief + Midday agreeing) is a stronger signal than either alone. The repeat count, source diversity, and temporal pattern are new information that only exists because of the grouping. Dedup that only saves vertical space is a missed opportunity.
