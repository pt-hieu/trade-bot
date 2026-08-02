---
name: project-economics
description: Placeholder. Cost and profit tracking for this project is not published. Use when reviewing infrastructure spend — then supply your own figures.
---

# Project Economics — redacted

The real contents of this skill are not published.

It tracked one person's actual brokerage account: realized profit and loss,
cash on hand, per-trade results, return on investment, and a dated ledger of
LLM vendor payments. None of that belongs in a public repository, and none of
it tells you anything useful about your own account.

## The method, without the numbers

The skill compared three running totals:

| Line | Source |
|---|---|
| Infrastructure cost | VM, DNS, database, edge hosting — mostly fixed per month |
| LLM inference cost | Per-run token spend, aggregated from trace data |
| Trading profit and loss | Realized results on closed positions, from the database |

The point of tracking all three together is that a pipeline which trades well
can still lose money if inference costs more than the edge is worth. Measure
both sides or you are guessing.

## If you are running your own copy

Write your own version. Pull cost from your vendors' billing APIs and profit
from your own trade records. Keep it private — an account balance is not
engineering documentation.
