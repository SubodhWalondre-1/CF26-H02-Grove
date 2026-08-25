from datetime import datetime
from typing import Optional

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Process-wide AsyncIOScheduler singleton
scheduler = AsyncIOScheduler()


async def start_scheduler() -> None:
    """
    Initializes and starts the APScheduler AsyncIOScheduler instance on application startup.
    Registers the periodic safety-net sweep job.
    """
    scheduler.add_job(
        _ttl_sweep_job_wrapper,
        trigger="interval",
        seconds=settings.ttl_sweep_interval_seconds,
        id="ttl_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _diagnostic_ttl_sweep_wrapper,
        trigger="interval",
        seconds=settings.ttl_sweep_interval_seconds,
        id="diagnostic_ttl_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _diagnostic_calibration_sweep_wrapper,
        trigger="interval",
        seconds=60,
        id="diagnostic_calibration_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _transfer_ttl_sweep_wrapper,
        trigger="interval",
        seconds=settings.ttl_sweep_interval_seconds,
        id="transfer_ttl_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _idempotency_reconciliation_wrapper,
        trigger="interval",
        seconds=60,
        id="idempotency_reconciliation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _override_anomaly_scan_wrapper,
        trigger="interval",
        seconds=120,
        id="override_anomaly_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _shortage_threshold_sweep_wrapper,
        trigger="interval",
        seconds=60,
        id="shortage_threshold_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        f"APScheduler started (periodic safety-net sweep every {settings.ttl_sweep_interval_seconds}s, transfer, idempotency, and override sweeps active)"
    )


async def stop_scheduler() -> None:
    """
    Shuts down the APScheduler scheduler on application shutdown.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


def schedule_ttl_expiry(tx_id: str, hold_expires_at: datetime) -> None:
    """
    Registers a precise one-shot date-triggered job firing at hold_expires_at to expire a PREPARING hold.
    """
    try:
        scheduler.add_job(
            _expire_hold_job,
            trigger="date",
            run_date=hold_expires_at,
            args=[tx_id],
            id=f"ttl_expire_{tx_id}",
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.debug(
            f"Scheduled live TTL expiry job for TX {tx_id} at {hold_expires_at}"
        )
    except Exception as e:
        logger.warning(
            f"Could not schedule live TTL expiry for TX {tx_id} (fallback to periodic sweep): {e}"
        )


def cancel_ttl_expiry(tx_id: str) -> None:
    """
    Cancels any scheduled TTL expiry job for a transaction that committed, rolled back, or completed.
    """
    try:
        scheduler.remove_job(f"ttl_expire_{tx_id}")
    except JobLookupError:
        pass
    except Exception as e:
        logger.debug(f"Error removing TTL expiry job for {tx_id}: {e}")


async def _ttl_sweep_job_wrapper() -> None:
    """
    Periodic worker job wrapper executing background safety-net sweeps.
    """
    from app.core.database import AsyncSessionLocal
    from app.engine import recovery

    async with AsyncSessionLocal() as db:
        try:
            await recovery.run_ttl_sweep(db)
        except Exception:
            logger.exception("Periodic TTL safety-net sweep encountered an error")


async def _expire_hold_job(tx_id: str) -> None:
    """
    Target callable for exact one-shot date-triggered TTL expiration.
    """
    from app.core.database import AsyncSessionLocal
    from app.engine import recovery

    async with AsyncSessionLocal() as db:
        try:
            await recovery.expire_hold(db, tx_id, reason="TTL_EXPIRED")
        except Exception:
            logger.exception(f"Target TTL expiration job failed for TX {tx_id}")


async def _diagnostic_ttl_sweep_wrapper() -> None:
    """
    Periodic worker job for diagnostic appointments TTL & No-Show sweeps.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.services.diagnostics_scheduling import DiagnosticsSchedulingService

    async with AsyncSessionLocal() as db:
        try:
            redis_client = await get_redis()
            service = DiagnosticsSchedulingService(db, redis_client)
            await service.sweep_expired_appointment_holds()
            await service.sweep_no_show_appointments()
            await db.commit()
        except Exception:
            logger.exception("Periodic diagnostic TTL/no-show sweep encountered an error")


async def _diagnostic_calibration_sweep_wrapper() -> None:
    """
    Periodic worker job checking equipment calibrations.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.services.diagnostics_scheduling import DiagnosticsSchedulingService

    async with AsyncSessionLocal() as db:
        try:
            redis_client = await get_redis()
            service = DiagnosticsSchedulingService(db, redis_client)
            await service.check_and_alert_calibrations()
            await db.commit()
        except Exception:
            logger.exception("Periodic diagnostic calibration sweep encountered an error")


async def _transfer_ttl_sweep_wrapper() -> None:
    """
    Periodic worker job for Patient Transfer TTL expiration sweeps.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.services.transfer import TransferService

    async with AsyncSessionLocal() as db:
        try:
            redis_client = await get_redis()
            service = TransferService(db, redis_client)
            await service.sweep_expired_transfers()
            await db.commit()
        except Exception:
            logger.exception("Periodic transfer TTL sweep encountered an error")


async def _idempotency_reconciliation_wrapper() -> None:
    """
    Periodic worker job for Idempotency Key reconciliation.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.engine.idempotency import reconcile_idempotency_keys

    async with AsyncSessionLocal() as db:
        try:
            redis_client = await get_redis()
            await reconcile_idempotency_keys(db, redis_client)
            await db.commit()
        except Exception:
            logger.exception("Periodic idempotency reconciliation encountered an error")


async def _override_anomaly_scan_wrapper() -> None:
    """
    Periodic worker job for Emergency Override anomaly scans.
    """
    from app.core.database import AsyncSessionLocal
    from app.engine.override import scan_post_hoc_acuity_mismatches

    async with AsyncSessionLocal() as db:
        try:
            await scan_post_hoc_acuity_mismatches(db)
            await db.commit()
        except Exception:
            logger.exception("Periodic override anomaly scan encountered an error")


async def _shortage_threshold_sweep_wrapper() -> None:
    """
    Periodic worker job evaluating consumable inventory against shortage thresholds.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.services.shortage import check_all_shortage_thresholds

    async with AsyncSessionLocal() as db:
        try:
            redis_client = await get_redis()
            await check_all_shortage_thresholds(db, redis_client)
        except Exception:
            logger.exception("Periodic shortage threshold sweep encountered an error")

