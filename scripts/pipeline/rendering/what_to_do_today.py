"""Deterministic WHAT TO DO TODAY renderer.

Before 2026-04-15 (MON-2026-04-16-002), synthesis_picks authored this
section as free-text LLM bullets and regularly paraphrase-drifted — the
canonical reproduction was a brief that wrote "HOLD FPT" while
MY HOLDINGS chose "TRIM 30% FPT". Root cause: the LLM read a stale
MINDSET block ("FPT, TCB HOLD positions from March 5") and dutifully
echoed it.

Fix: render WHAT TO DO TODAY deterministically from the authoritative
`list[HoldingAction]` + today's picks. No LLM, no paraphrase drift.
"""

from __future__ import annotations

import logfire

from shared.rules.audit_tags import strip_audit_tags
from shared.rules.exit_strategy import format_rr_display, is_trailing_exit, read_rr
from shared.text_utils import split_first_sentence

from .models import HoldingAction


def _holding_bullet(action: HoldingAction) -> str:
    """Render one HoldingAction as a WHAT TO DO TODAY bullet."""

    verb = action.bullet_verb()  # already includes ticker + qty%
    parts: list[str] = [f"- {verb}"]
    rationale = strip_audit_tags(action.rationale)
    if rationale:
        # First sentence only, capped so decimals like "84.5k" don't get split.
        trimmed = split_first_sentence(rationale, max_len=140)
        if trimmed:
            parts.append(f" — {trimmed}")
    # Stop reference only meaningful for active adjustments — HOLD bullets
    # already reference catastrophic stops in MY HOLDINGS prose.
    if action.stop_price_vnd and action.verb in ("TRIM", "EXIT", "ADD"):
        parts.append(f" (stop {action.stop_price_vnd:,} VND)")
    return "".join(parts)


def _pick_bullets(top_picks: list[dict] | None) -> list[str]:
    """Render one BUY bullet per pre-computed pick candidate.

    No cap here (SWI-274) — `top_picks` is `pre_computed_picks`, already
    BUY-first / R:R-sorted and bounded upstream by `extract_top_picks`
    (<=5 by goal-urgency tier), so every TOP PICKS BUY surfaces.
    """

    if not top_picks:
        return []
    bullets: list[str] = []
    for pick in top_picks:
        ticker = pick.get("ticker") or "?"
        entry = pick.get("entry_price_vnd") or pick.get("entry") or 0
        note = pick.get("why") or pick.get("reason") or ""
        note_snippet = split_first_sentence(note, max_len=120)
        entry_str = f"{int(entry):,}" if entry else "TBD"
        suffix = f" — {note_snippet}" if note_snippet else ""

        # Boundary contract: pick must carry exit_family for is_trailing_exit()
        # to dispatch correctly. Absent → falls back to `target is None`, which
        # collapses producer-leak with intentional trailing.
        if "exit_family" not in pick:
            logfire.warn(
                "PICK_PAYLOAD_MISSING_EXIT_FAMILY",
                ticker=ticker,
                site="what_to_do_today._pick_bullets",
            )

        rr = read_rr(pick)
        if rr is None and not is_trailing_exit(pick):
            # Non-trailing pick with no R:R = upstream producer leaked None on
            # a fixed-target setup (4th-instance defect class — SWI-115/317/340).
            logfire.warn(
                "ATR_TRAIL_PRODUCER_LEAK",
                ticker=ticker,
                strategy=pick.get("strategy"),
                exit_family=pick.get("exit_family"),
                site="what_to_do_today._pick_bullets",
            )
            rr_disp = "n/a"
        else:
            rr_disp = format_rr_display(rr)
        bullets.append(f"- BUY {ticker} at {entry_str} (R:R {rr_disp}){suffix}")
    return bullets


def render_what_to_do_today(
    holdings_actions: list[HoldingAction],
    top_picks: list[dict] | None = None,
    key_risk: str | None = None,
    min_rr_floor: float | None = None,
    max_new_entries: int | None = None,
    watch_hint: str | None = None,
) -> str:
    """Render WHAT TO DO TODAY as plain ASCII bullets.

    Fixed bullet order (determinism eliminates drift):
      1. One bullet per non-HOLD holding decision, ordered by urgency.
      2. HOLD-only summary line (if any holdings remain after (1)).
      3. One execution bullet per pick (or a WAIT line if 0 picks).
      4. Key risk monitoring bullet.
      5. Capital preservation / R:R floor / sizing discipline bullet.
    """
    lines: list[str] = ["WHAT TO DO TODAY"]

    # --- 1. Non-HOLD actions, urgency-sorted ---------------------------------
    urgency_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    non_hold = [a for a in holdings_actions if a.verb != "HOLD"]
    non_hold.sort(key=lambda a: (urgency_rank.get(a.urgency, 3), a.ticker))
    for action in non_hold:
        lines.append(_holding_bullet(action))

    # --- 2. HOLD summary (collapsed into one line) ----------------------------
    hold_only = [a for a in holdings_actions if a.verb == "HOLD"]
    if hold_only:
        tickers = ", ".join(a.ticker for a in hold_only)
        lines.append(f"- HOLD {tickers} through today; monitor catastrophic stops only")

    # --- 3. Pick execution OR WAIT -------------------------------------------
    # SWI-327: drop picks whose genuine R:R is below today's floor before
    # rendering BUY bullets, so a sub-floor pick cannot surface as an
    # actionable BUY while the discipline line states any new BUY must clear
    # the floor. R:R-unknown picks are deliberately KEPT: trailing exits carry
    # no fixed R:R by design, and a None on a fixed-target is a producer leak
    # the brief intentionally surfaces as `R:R n/a` — neither should be
    # silently filtered. Only a numeric R:R below the floor is dropped.
    floor_qualified_picks = []
    for pick in top_picks or []:
        rr = read_rr(pick)
        if min_rr_floor is None or rr is None or rr >= min_rr_floor:
            floor_qualified_picks.append(pick)
    pick_lines = _pick_bullets(floor_qualified_picks)
    if pick_lines:
        lines.extend(pick_lines)
    else:
        wait_hint = watch_hint or (
            f"WAIT: no setups meet R:R >= {min_rr_floor:.1f} today — "
            f"place alerts at support, do not chase"
            if min_rr_floor
            else "WAIT: no setups meet today's R:R floor — place alerts, do not chase"
        )
        lines.append(f"- {wait_hint}")

    # --- 4. Key risk monitoring ----------------------------------------------
    if key_risk:
        key_risk_snippet = split_first_sentence(key_risk, max_len=140)
        if key_risk_snippet:
            lines.append(f"- Monitor key risk: {key_risk_snippet}")

    # --- 5. Capital preservation / discipline --------------------------------
    if max_new_entries is not None and max_new_entries == 0:
        lines.append("- Capital preservation: max 0 new entries today; no exceptions")
    else:
        floor_hint = f"R:R >= {min_rr_floor:.1f}" if min_rr_floor else "today's R:R floor"
        lines.append(f"- Discipline: any new BUY must clear {floor_hint} and pass the entry gate")

    return "\n".join(lines)
