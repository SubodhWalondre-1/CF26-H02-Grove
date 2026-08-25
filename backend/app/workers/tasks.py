import asyncio
from datetime import datetime
from typing import Any, Dict

from celery import Celery

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

celery_app = Celery(
    "mediora",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(
    name="mediora.run_crash_recovery_scan",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def run_crash_recovery_scan_task(self, triggered_by: str = "startup") -> Dict[str, Any]:
    """
    Synchronous Celery task executing an asynchronous crash recovery scan.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.engine import recovery

        async with AsyncSessionLocal() as db:
            return await recovery.run_crash_recovery_scan(
                db=db,
                triggered_by=triggered_by,
            )

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("run_crash_recovery_scan_task failed")
        raise self.retry(exc=exc)

    # Format datetime instances for JSON serialization
    if isinstance(result.get("started_at"), datetime):
        result["started_at"] = result["started_at"].isoformat()
    if isinstance(result.get("completed_at"), datetime):
        result["completed_at"] = result["completed_at"].isoformat()

    logger.info(
        f"Recovery scan complete: run_id={result.get('run_id')} "
        f"scanned={result.get('scanned_count')} resolved={result.get('resolved_count')}"
    )

    return result


@celery_app.task(
    name="mediora.expire_pharmacy_batches",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def expire_pharmacy_batches_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Daily sweep: mark expired pharmacy batches, zero available_quantity,
    trigger shortage recheck.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.services.pharmacy import PharmacyService

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = PharmacyService(db, redis_client)
            expired_batch_ids = await service.expire_stale_batches()
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "expired_count": len(expired_batch_ids),
                "expired_batch_ids": expired_batch_ids,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("expire_pharmacy_batches_task failed")
        raise self.retry(exc=exc)

    logger.info(
        f"Pharmacy expiry sweep complete: expired={result.get('expired_count')}"
    )
    return result


@celery_app.task(
    name="mediora.sweep_pharmacy_ttl",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def sweep_pharmacy_ttl_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic sweep: release RESERVED pharmacy reservations past ttl_expires_at.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.services.pharmacy import PharmacyService

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = PharmacyService(db, redis_client)
            released_count = await service.sweep_expired_reservations()
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "released_count": released_count,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("sweep_pharmacy_ttl_task failed")
        raise self.retry(exc=exc)

    logger.info(
        f"Pharmacy TTL sweep complete: released={result.get('released_count')}"
    )
    return result


@celery_app.task(
    name="mediora.sweep_appointment_ttl",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def sweep_appointment_ttl_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic sweep: cancel PENDING_CONFIRM appointments past hold_ttl_expires_at
    and mark no-shows on unstarted CONFIRMED appointments.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.services.diagnostics_scheduling import DiagnosticsSchedulingService

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = DiagnosticsSchedulingService(db, redis_client)
            expired_holds = await service.sweep_expired_appointment_holds()
            no_shows = await service.sweep_no_show_appointments()
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "expired_holds": expired_holds,
                "no_shows_marked": no_shows,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("sweep_appointment_ttl_task failed")
        raise self.retry(exc=exc)

    return result


@celery_app.task(
    name="mediora.flag_stuck_lab_samples",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def flag_stuck_lab_samples_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic sweep: flag PROCESSING lab samples exceeding 2x turnaround estimate.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.services.lab_queue import LabQueueService

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = LabQueueService(db, redis_client)
            stuck_ids = await service.sweep_stuck_samples()
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "stuck_samples_flagged": len(stuck_ids),
                "stuck_sample_ids": stuck_ids,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("flag_stuck_lab_samples_task failed")
        raise self.retry(exc=exc)

    return result


@celery_app.task(
    name="mediora.check_calibration_due",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def check_calibration_due_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic sweep: verify diagnostic equipment calibrations and transition overdue machines.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.services.diagnostics_scheduling import DiagnosticsSchedulingService

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = DiagnosticsSchedulingService(db, redis_client)
            alerted = await service.check_and_alert_calibrations()
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "alerted_equipment": alerted,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("check_calibration_due_task failed")
        raise self.retry(exc=exc)

    return result


@celery_app.task(
    name="mediora.sweep_transfer_ttl",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def sweep_transfer_ttl_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic sweep: auto-rollback patient transfers past hold_ttl_expires_at,
    restoring the source bed to IN_USE with patient re-attached.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.services.transfer import TransferService

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = TransferService(db, redis_client)
            rolled_back_count = await service.sweep_expired_transfers()
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "transfers_rolled_back": rolled_back_count,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("sweep_transfer_ttl_task failed")
        raise self.retry(exc=exc)

    return result


@celery_app.task(
    name="mediora.reconcile_idempotency_keys",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def reconcile_idempotency_keys_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic recovery task: scans orphaned PENDING idempotency keys and reconciles them.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.core.redis import get_redis
        from app.engine.idempotency import reconcile_idempotency_keys

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            reconciled = await reconcile_idempotency_keys(db, redis_client)
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "keys_reconciled": reconciled,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("reconcile_idempotency_keys_task failed")
        raise self.retry(exc=exc)

    return result


@celery_app.task(
    name="mediora.flag_override_anomalies",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def flag_override_anomalies_task(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
    """
    Periodic governance task: scans manual-declare overrides for post-hoc acuity mismatches.
    """
    async def _run() -> Dict[str, Any]:
        from app.core.database import AsyncSessionLocal
        from app.engine.override import scan_post_hoc_acuity_mismatches

        async with AsyncSessionLocal() as db:
            flagged = await scan_post_hoc_acuity_mismatches(db)
            await db.commit()
            return {
                "triggered_by": triggered_by,
                "events_flagged": flagged,
            }

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        logger.exception("flag_override_anomalies_task failed")
        raise self.retry(exc=exc)

    return result


@celery_app.task(
    name="mediora.generate_operation_record_pdf",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def generate_operation_record_pdf(self, tx_id: str) -> Dict[str, Any]:
    """
    Celery task to aggregate audit events and render Digital Operation Record PDF.
    Idempotent: updates or creates operation_records entry.
    """
    async def _run() -> Dict[str, Any]:
        from datetime import datetime, timezone
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.operation_record import OperationRecord
        from app.services.record import aggregate_operation_record
        from app.services.pdf_renderer import render_operation_record_pdf

        async with AsyncSessionLocal() as db:
            # 1. Check or create operation_records entry
            stmt = select(OperationRecord).where(OperationRecord.tx_id == tx_id)
            rec = (await db.execute(stmt)).scalar_one_or_none()
            if not rec:
                rec = OperationRecord(
                    tx_id=tx_id,
                    file_path="",
                    status="PENDING",
                    audit_id=f"AUD-{tx_id}",
                )
                db.add(rec)
                await db.flush()

            try:
                # 2. Aggregate audit events
                op_data = await aggregate_operation_record(tx_id=tx_id, db=db)

                # 3. Render PDF
                file_path, _ = render_operation_record_pdf(op_data)

                # 4. Update status to GENERATED
                rec.file_path = file_path
                rec.status = "GENERATED"
                rec.generated_at = datetime.now(timezone.utc)
                rec.error_message = None
                await db.commit()
                return {"tx_id": tx_id, "status": "GENERATED", "file_path": file_path}
            except Exception as e:
                logger.error(f"Failed to generate operation record PDF for tx={tx_id}: {e}", exc_info=True)
                rec.status = "FAILED"
                rec.error_message = str(e)
                await db.commit()
                return {"tx_id": tx_id, "status": "FAILED", "error": str(e)}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception(f"generate_operation_record_pdf fatal worker error for tx={tx_id}")
        return {"tx_id": tx_id, "status": "FAILED", "error": str(exc)}
