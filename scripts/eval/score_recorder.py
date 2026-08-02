"""Audit-row persistence for the BUY-candidate scoring framework.

Phase A wiring (SWI-171). Every candidate that reaches ``picks.py:122``
gets a row in ``pre_gate_candidates``, regardless of which rejection
layer (1-5) drops it. Score is the same across all layers — computed
deterministically up front, persisted unchanged.

Invocation seams:
  * ``scripts/agents/picks.py`` (layer 1-2 + survivors)
  * ``scripts/agents/picks_exit_dispatch.py`` (stamps drop kind on setup)
  * ``scripts/pipeline/recommendation_audit.py`` (validator outcome,
    layer 5)

The validator itself stays side-effect-free — this module owns every
write to ``pre_gate_candidates``.

Fail-open: each DB call is wrapped in try/except. A DB blip never
aborts the pipeline in audit mode.

In-memory side-store: ``dict[tuple[ticker, phase], StoredScore]``.
``(ticker, phase)`` tuple key prevents the midday revision from
overwriting morning's entry in the same run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from shared.database import get_db
from shared.neon._utils import safe_float
from shared.rules.scoring import GatedBy, ScoreResult, ScoringPhase

logger = logging.getLogger(__name__)


_INSERT_SQL = """
INSERT INTO pre_gate_candidates (
    scan_date, ticker, phase,
    score, breakdown, base_score, regime_penalty, shock_penalty,
    threshold_at_run, weights_jsonb, scoring_version,
    gated_by, gate_reason, would_pass_score_gate,
    feature_risk_reward, feature_sim_p_target, feature_sim_p_stop,
    feature_sim_ev, feature_strategy_confidence, feature_belief_conviction,
    feature_catalyst_strength, feature_bullish_belief_count,
    feature_total_sector_count, feature_rs_20d, feature_volume_vs_avg,
    feature_trend_alignment, feature_foreign_net_strength,
    feature_order_imbalance,
    relief_eligible, relief_block_reason,
    sector, source, regime, urgency_tier
)
VALUES (
    $1, $2, $3::scoring_phase,
    $4, $5, $6, $7, $8,
    $9, $10, $11,
    $12::gated_by_kind, $13, $14,
    $15, $16, $17,
    $18, $19, $20,
    $21, $22,
    $23, $24, $25,
    $26, $27,
    $28,
    $29, $30,
    $31, $32::candidate_source, $33, $34
)
ON CONFLICT (scan_date, ticker, phase) DO UPDATE
  SET score = EXCLUDED.score,
      breakdown = EXCLUDED.breakdown,
      base_score = EXCLUDED.base_score,
      regime_penalty = EXCLUDED.regime_penalty,
      shock_penalty = EXCLUDED.shock_penalty,
      threshold_at_run = EXCLUDED.threshold_at_run,
      weights_jsonb = EXCLUDED.weights_jsonb,
      scoring_version = EXCLUDED.scoring_version,
      gated_by = EXCLUDED.gated_by,
      gate_reason = EXCLUDED.gate_reason,
      would_pass_score_gate = EXCLUDED.would_pass_score_gate,
      feature_risk_reward = EXCLUDED.feature_risk_reward,
      feature_sim_p_target = EXCLUDED.feature_sim_p_target,
      feature_sim_p_stop = EXCLUDED.feature_sim_p_stop,
      feature_sim_ev = EXCLUDED.feature_sim_ev,
      feature_strategy_confidence = EXCLUDED.feature_strategy_confidence,
      feature_belief_conviction = EXCLUDED.feature_belief_conviction,
      feature_catalyst_strength = EXCLUDED.feature_catalyst_strength,
      feature_bullish_belief_count = EXCLUDED.feature_bullish_belief_count,
      feature_total_sector_count = EXCLUDED.feature_total_sector_count,
      feature_rs_20d = EXCLUDED.feature_rs_20d,
      feature_volume_vs_avg = EXCLUDED.feature_volume_vs_avg,
      feature_trend_alignment = EXCLUDED.feature_trend_alignment,
      feature_foreign_net_strength = EXCLUDED.feature_foreign_net_strength,
      feature_order_imbalance = EXCLUDED.feature_order_imbalance,
      relief_eligible = EXCLUDED.relief_eligible,
      relief_block_reason = EXCLUDED.relief_block_reason,
      sector = EXCLUDED.sector,
      source = EXCLUDED.source,
      regime = EXCLUDED.regime,
      urgency_tier = EXCLUDED.urgency_tier
"""


_UPDATE_OUTCOME_SQL = """
UPDATE pre_gate_candidates
   SET gated_by    = $1::gated_by_kind,
       gate_reason = $2
 WHERE scan_date = $3
   AND ticker    = $4
   AND phase     = $5::scoring_phase
   AND (gated_by IS DISTINCT FROM $1::gated_by_kind
        OR gate_reason IS DISTINCT FROM $2)
"""


@dataclass(frozen=True)
class StoredScore:
    """Score + metadata needed to re-stamp the audit row later.

    Relief decisions are not duplicated — they live on ``result``
    (``relief_suppressed`` + ``relief_block_reason``). Held in the
    in-memory side-store so the validator wrapper (layer 5) can re-write
    the row's ``gated_by`` without re-deriving features.
    """

    result: ScoreResult
    feature_values: dict[str, object]
    regime: str
    sector: str | None
    source: str
    urgency_tier: str | None


@dataclass
class ScoreRecorder:
    """Per-pipeline-run audit recorder + in-memory side-store."""

    scan_date: date
    side_store: dict[tuple[str, ScoringPhase], StoredScore] = field(default_factory=dict)

    @classmethod
    def for_run(cls, scan_date: date) -> ScoreRecorder:
        return cls(scan_date=scan_date)

    def remember(self, ticker: str, phase: ScoringPhase, stored: StoredScore) -> None:
        self.side_store[(ticker.upper(), phase)] = stored

    def recall(self, ticker: str, phase: ScoringPhase) -> StoredScore | None:
        return self.side_store.get((ticker.upper(), phase))

    async def record(
        self,
        *,
        ticker: str,
        phase: ScoringPhase,
        result: ScoreResult,
        gated_by: GatedBy,
        gate_reason: str | None,
        regime: str,
        sector: str | None = None,
        source: str = "sector",
        urgency_tier: str | None = None,
        feature_values: dict[str, object] | None = None,
    ) -> None:
        """Insert (or upsert) the audit row + cache the bundle in-memory.

        Fail-open on DB error: log a warning and return.
        """
        ticker_upper = ticker.upper()
        stored = StoredScore(
            result=result,
            feature_values=dict(feature_values or {}),
            regime=regime,
            sector=sector,
            source=source if source in ("sector", "belief_fallback") else "sector",
            urgency_tier=urgency_tier,
        )
        self.remember(ticker_upper, phase, stored)

        try:
            await self._insert(
                ticker=ticker_upper,
                phase=phase,
                stored=stored,
                gated_by=gated_by,
                gate_reason=gate_reason,
            )
        except Exception as exc:
            logger.warning(
                "score_recorder: insert failed for %s phase=%s gated_by=%s: %s",
                ticker_upper,
                phase,
                gated_by,
                exc,
                exc_info=True,
            )

    async def update_outcome(
        self,
        *,
        ticker: str,
        phase: ScoringPhase,
        gated_by: GatedBy,
        gate_reason: str | None,
    ) -> bool:
        """Re-stamp ``gated_by`` for layer-5 outcomes via a targeted UPDATE.

        Cheaper than re-inserting the full 34-column row when the only
        change is the verdict. Returns True when the side-store has a
        prior write for this ``(ticker, phase)``, False otherwise.

        Fail-open on DB error: log a warning and return ``True`` (the
        caller treated the side-store hit as authoritative even if the
        DB write fails).
        """
        ticker_upper = ticker.upper()
        if self.recall(ticker_upper, phase) is None:
            return False
        try:
            db = await get_db()
            await db.execute(
                _UPDATE_OUTCOME_SQL,
                gated_by,
                gate_reason,
                self.scan_date,
                ticker_upper,
                phase,
            )
        except Exception as exc:
            logger.warning(
                "score_recorder: update_outcome failed for %s phase=%s gated_by=%s: %s",
                ticker_upper,
                phase,
                gated_by,
                exc,
                exc_info=True,
            )
        return True

    async def _insert(
        self,
        *,
        ticker: str,
        phase: ScoringPhase,
        stored: StoredScore,
        gated_by: GatedBy,
        gate_reason: str | None,
    ) -> None:
        result = stored.result
        features = stored.feature_values
        threshold = result.threshold
        would_pass = bool(result.score >= threshold) if threshold > 0 else False

        db = await get_db()
        await db.execute(
            _INSERT_SQL,
            self.scan_date,
            ticker,
            phase,
            float(result.score),
            result.to_jsonb(),
            float(result.base_score),
            float(result.regime_penalty),
            float(result.shock_penalty),
            int(threshold),
            result.weights_snapshot,
            result.scoring_version,
            gated_by,
            gate_reason,
            would_pass,
            safe_float(features.get("risk_reward")),
            safe_float(features.get("sim_p_target")),
            safe_float(features.get("sim_p_stop")),
            safe_float(features.get("sim_ev")),
            safe_float(features.get("strategy_confidence")),
            safe_float(features.get("belief_conviction")),
            safe_float(features.get("catalyst_strength")),
            _opt_int(features.get("bullish_sector_belief_count")),
            _opt_int(features.get("total_sector_count")),
            safe_float(features.get("rs_20d")),
            safe_float(features.get("volume_vs_avg")),
            _opt_str(features.get("trend_alignment")),
            safe_float(features.get("foreign_net_strength")),
            safe_float(features.get("order_imbalance")),
            bool(result.relief_suppressed),
            result.relief_block_reason,
            stored.sector,
            stored.source,
            stored.regime,
            stored.urgency_tier,
        )


async def record_signals_audit(
    scan_date: date,
    phase: ScoringPhase,
    sector_signals: list[dict],
    sector_beliefs: list[dict] | None = None,
) -> None:
    """Per-sector BULLISH belief denominator BEFORE the picks loop runs.

    Closes round-3 architectural #4 — distinguishes "we considered N
    beliefs upstream" from "the picks loop filtered out N candidates".
    Fail-open.
    """
    if not sector_signals and not sector_beliefs:
        return

    buckets: dict[str, dict[str, int]] = {}

    def _bucket(sector: str) -> dict[str, int]:
        return buckets.setdefault(
            sector,
            {"total_signal_count": 0, "buy_signal_count": 0, "bullish_belief_count": 0},
        )

    for signal in sector_signals or []:
        sector = signal.get("sector") or "UNKNOWN"
        bucket = _bucket(sector)
        bucket["total_signal_count"] += 1
        if (signal.get("signal") or "").upper() == "BUY":
            bucket["buy_signal_count"] += 1

    for belief in sector_beliefs or []:
        if (belief.get("direction") or "").upper() != "BULLISH":
            continue
        sector = belief.get("sector") or "UNKNOWN"
        _bucket(sector)["bullish_belief_count"] += 1

    if not buckets:
        return

    rows = [
        (
            scan_date,
            phase,
            sector,
            int(counts["bullish_belief_count"]),
            int(counts["total_signal_count"]),
            int(counts["buy_signal_count"]),
        )
        for sector, counts in buckets.items()
    ]

    try:
        db = await get_db()
        await db.execute_many(
            """
            INSERT INTO signals_audit (
                scan_date, phase, sector,
                bullish_belief_count, total_signal_count, buy_signal_count
            )
            VALUES ($1, $2::scoring_phase, $3, $4, $5, $6)
            ON CONFLICT (scan_date, phase, sector) DO UPDATE
              SET bullish_belief_count = EXCLUDED.bullish_belief_count,
                  total_signal_count = EXCLUDED.total_signal_count,
                  buy_signal_count = EXCLUDED.buy_signal_count
            """,
            rows,
        )
    except Exception as exc:
        logger.warning("signals_audit write failed for %s phase=%s: %s", scan_date, phase, exc)


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _opt_str(value: object) -> str | None:
    return str(value) if value is not None else None


__all__ = ["ScoreRecorder", "StoredScore", "record_signals_audit"]
