"""Phase 2 post-processing: persist beliefs, alerts, and checkpoint."""

import logging
from datetime import date

from shared.env import is_production
from shared.observability import log_warn
from shared.rules.belief_coverage import (
    EXPECTED_POSITION_AGENT_KEYS,
    EXPECTED_SECTOR_AGENT_KEYS,
    OPTIONAL_POSITION_AGENT_KEYS,
    OPTIONAL_SECTOR_AGENT_KEYS,
    assert_belief_coverage,
)

from .types import DeterministicBeliefs

logger = logging.getLogger(__name__)


async def persist_phase2_results(
    phase2_results,
    scan_date: date,
    total_sector_count: int,
    workflow_config: dict | None = None,
    global_macro_regime: str | None = None,
    expected_sector_tickers: frozenset[str] | None = None,
    expected_position_tickers: frozenset[str] | None = None,
) -> DeterministicBeliefs:
    """Persist beliefs, alerts, checkpoint after Phase 2. Returns deterministic_beliefs."""
    sector_results = phase2_results.sector_results
    position_alerts = phase2_results.position_alerts or {"alerts": []}

    if phase2_results.all_sectors_failed:
        logger.critical(
            "Total Phase 2 failure: all %d sectors failed, 0 signals.",
            len(sector_results),
        )

    # Carry forward sector beliefs when EXIT_ONLY skips sector agents
    workflow_type = (workflow_config or {}).get("workflow_type", "")
    is_carry_forward_path = workflow_type == "EXIT_ONLY"
    if not phase2_results.sector_beliefs and is_carry_forward_path:
        try:
            from shared.neon.beliefs import carry_forward_beliefs

            crisis_mode = global_macro_regime == "CRISIS"
            phase2_results.sector_beliefs = await carry_forward_beliefs(
                scan_date, "sector", crisis_mode=crisis_mode
            )
        except Exception as e:
            logger.warning("Sector belief carry-forward failed (non-fatal): %s", e)
            log_warn(
                "SECTOR_BELIEF_CARRY_FORWARD_FAILED",
                scope="phase_postprocess",
                scan_date=str(scan_date),
                error=str(e),
            )

    # Persist beliefs. insert_agent_beliefs now raises on DB failure (A5a),
    # so failure of persistence kills the morning run rather than silently
    # producing recommendations without belief backing.
    from shared.neon import insert_agent_beliefs

    belief_groups = (
        ("sector", phase2_results.sector_beliefs),
        ("positions", phase2_results.position_beliefs),
    )
    total_beliefs = 0
    for ensemble_type, beliefs in belief_groups:
        if not beliefs:
            continue
        await insert_agent_beliefs(scan_date, beliefs, ensemble_type)
        total_beliefs += len(beliefs)
    if total_beliefs:
        print(f"  Persisted {total_beliefs} agent beliefs to DB")

    # Post-insert coverage assertion — LIVE path only. Carry-forward
    # bypasses the sub-agent Pydantic model and may legitimately return
    # fewer agent_keys, so skip this check on EXIT_ONLY days.
    if not is_carry_forward_path:
        assert_belief_coverage(
            phase2_results.sector_beliefs or [],
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=logger,
            optional_keys=OPTIONAL_SECTOR_AGENT_KEYS,
            expected_tickers=expected_sector_tickers,
        )
        assert_belief_coverage(
            phase2_results.position_beliefs or [],
            EXPECTED_POSITION_AGENT_KEYS,
            ensemble_label="positions",
            logger=logger,
            optional_keys=OPTIONAL_POSITION_AGENT_KEYS,
            expected_tickers=expected_position_tickers,
        )

    # Deterministic belief post-processing
    deterministic_beliefs: DeterministicBeliefs = {"sector": [], "positions": []}
    try:
        from pipeline.phase_beliefs import post_process_beliefs

        raw_deterministic = await post_process_beliefs(
            scan_date, phase2_results.sector_beliefs, phase2_results.position_beliefs
        )
        deterministic_beliefs = {
            "sector": raw_deterministic.get("sector") or [],
            "positions": raw_deterministic.get("positions") or [],
            "calibration_stats": raw_deterministic.get("calibration_stats") or {},
        }
        deterministic_count = len(deterministic_beliefs["sector"]) + len(
            deterministic_beliefs["positions"]
        )
        if deterministic_count:
            print(f"  Deterministic aggregation: {deterministic_count} beliefs")
    except Exception as e:
        # Production survives on raw beliefs; CI/dev surfaces the failure.
        logger.warning("Deterministic belief post-processing failed (non-fatal): %s", e)
        log_warn(
            "DETERMINISTIC_BELIEF_POST_PROCESS_FAILED",
            scope="phase_postprocess",
            scan_date=str(scan_date),
            error=str(e),
        )
        if not is_production():
            raise

    # Persist position alerts
    alerts = position_alerts.get("alerts") or []
    urgent = [alert for alert in alerts if alert.get("urgency") == "high"]
    print(f"\nSector analyses: {len(sector_results)} completed")
    print(f"Position alerts: {len(alerts)} total, {len(urgent)} urgent")
    if alerts:
        try:
            from shared.neon import insert_morning_position_alerts

            persisted = await insert_morning_position_alerts(scan_date, alerts)
            print(f"  Persisted {persisted} position alerts to DB")
        except Exception as e:
            logger.warning("Position alert persistence error (non-fatal): %s", e)
            print(f"  Position alert persistence error (non-fatal): {e}")
            log_warn(
                "POSITION_ALERT_PERSIST_FAILED",
                scope="phase_postprocess",
                scan_date=str(scan_date),
                error=str(e),
            )

    # Checkpoint Phase 2
    try:
        from shared.neon.checkpoints import save_checkpoint

        saved = await save_checkpoint(
            scan_date=scan_date,
            phase="phase2",
            data=phase2_results.to_dict(),
            failed_sector_count=phase2_results.failed_sector_count,
            total_sector_count=total_sector_count,
        )
        if saved:
            print("  Phase 2 checkpoint saved to DB")
    except Exception as checkpoint_error:
        logger.warning("Phase 2 checkpoint save failed (non-fatal): %s", checkpoint_error)
        log_warn(
            "PHASE2_CHECKPOINT_SAVE_FAILED",
            scope="phase_postprocess",
            scan_date=str(scan_date),
            error=str(checkpoint_error),
        )

    return deterministic_beliefs
