"""
Idempotency Gate Engine — Feature #17

Guarantees that identical rapid-fire requests never create duplicate transactions
or double-allocate resources.

Key Features:
  • Deterministic SHA-256 fingerprinting with 10s time-window bucketing.
  • Atomic Redis claims (SET ... NX EX <ttl>) eliminating check-then-set race conditions.
  • Outcome-based dynamic TTL policy:
      - COMMITTED/DISPENSED/APPROVED: Retains full TTL (protects grants).
      - REJECTED/FAILED: Shortened to 2-second grace window (allows fast retry).
      - ROLLED_BACK/EXPIRED: Deleted immediately.
  • Durable PostgreSQL ledger (idempotency_keys) with duplicate hit tracking.
  • Background Celery / scheduler reconciliation worker.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKey, IdempotencyStatus
from app.models.models import Transaction
from app.services.audit import create_audit_event

logger = logging.getLogger(__name__)


@dataclass
class ClaimResult:
    is_duplicate: bool
    fingerprint: str
    existing_tx_id: Optional[str] = None
    existing_status: Optional[str] = None
    claimed_by: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# 1. FINGERPRINT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def build_fingerprint(
    request_type: str,
    fields: Dict[str, Any],
    bucket_seconds: int = 10,
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for a request.
    Floors timestamp to bucket_seconds to collapse rapid-fire duplicates.
    """
    current_bucket = int(time.time() // bucket_seconds) * bucket_seconds
    req_type_norm = request_type.lower()

    # Extract & sort resources
    resources = fields.get("resource_ids") or []
    if not resources and fields.get("resource_id"):
        resources = [fields.get("resource_id")]
    sorted_resources = ",".join(sorted(str(r) for r in resources))

    patient_id = str(fields.get("patient_id", ""))

    components: List[str] = [
        f"type={req_type_norm}",
        f"patient={patient_id}",
    ]

    if sorted_resources:
        components.append(f"resources={sorted_resources}")

    # Transfer specific fields
    if "source_bed_id" in fields and "destination_bed_id" in fields:
        components.append(f"source={fields.get('source_bed_id')}")
        components.append(f"dest={fields.get('destination_bed_id')}")
        if fields.get("transport_resource_id"):
            components.append(f"transport={fields.get('transport_resource_id')}")

    # Escalation specific fields
    if "target_resource_id" in fields:
        components.append(f"target={fields.get('target_resource_id')}")

    # Pharmacy specific fields
    if "requested_quantity" in fields:
        components.append(f"qty={fields.get('requested_quantity')}")

    # Diagnostics specific fields
    if "scheduled_start" in fields and "scheduled_end" in fields:
        components.append(f"window={fields.get('scheduled_start')}_{fields.get('scheduled_end')}")

    # Append time bucket
    components.append(f"bucket={current_bucket}")

    raw_string = "|".join(components)
    return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 2. ATOMIC CLAIM
# ─────────────────────────────────────────────────────────────────────────────

async def check_and_claim(
    redis_client: Optional[aioredis.Redis],
    db: AsyncSession,
    request_type: str,
    fields: Dict[str, Any],
    claimed_by: str,
    default_ttl_seconds: int = 30,
) -> ClaimResult:
    """
    Performs an atomic claim in Redis using SET ... NX EX <ttl>.
    If key exists, increments duplicate_hits and returns duplicate status.
    """
    now_utc = datetime.now(timezone.utc)
    fp = build_fingerprint(request_type, fields)
    redis_key = f"idem:{request_type}:{fp}"
    expires_at = now_utc + timedelta(seconds=default_ttl_seconds)

    if redis_client:
        payload = {
            "tx_id": "PENDING",
            "status": "PENDING",
            "claimed_by": claimed_by,
            "claimed_at": now_utc.isoformat(),
        }
        # Atomic claim
        claimed = await redis_client.set(
            redis_key,
            json.dumps(payload),
            nx=True,
            ex=default_ttl_seconds,
        )

        if claimed:
            # First-time claim: Record in PostgreSQL ledger
            ledger_entry = IdempotencyKey(
                fingerprint=fp,
                request_type=request_type,
                tx_id="PENDING",
                claimed_by=claimed_by,
                status=IdempotencyStatus.PENDING.value,
                claimed_at=now_utc,
                expires_at=expires_at,
                duplicate_hits=0,
            )
            db.add(ledger_entry)
            await db.flush()

            return ClaimResult(is_duplicate=False, fingerprint=fp)
        else:
            # Duplicate hit!
            existing_raw = await redis_client.get(redis_key)
            existing_tx_id = "PENDING"
            existing_status = "PENDING"
            original_claimer = claimed_by

            if existing_raw:
                try:
                    data = json.loads(existing_raw)
                    existing_tx_id = data.get("tx_id", "PENDING")
                    existing_status = data.get("status", "PENDING")
                    original_claimer = data.get("claimed_by", claimed_by)
                except Exception:
                    pass

            # Increment duplicate hits in DB
            upd_stmt = (
                update(IdempotencyKey)
                .where(IdempotencyKey.fingerprint == fp)
                .values(duplicate_hits=IdempotencyKey.duplicate_hits + 1)
            )
            await db.execute(upd_stmt)
            await db.flush()

            # Audit event
            await create_audit_event(
                db=db,
                event_type="DUPLICATE_REQUEST_SUPPRESSED",
                tx_id=existing_tx_id if existing_tx_id != "PENDING" else None,
                detail={
                    "fingerprint": fp,
                    "request_type": request_type,
                    "attempted_by": claimed_by,
                    "original_claimer": original_claimer,
                    "existing_status": existing_status,
                },
            )

            logger.info(
                f"Idempotency Gate: Suppressed duplicate {request_type} request (FP: {fp[:8]}...)",
                extra={"fingerprint": fp, "attempted_by": claimed_by, "existing_tx_id": existing_tx_id},
            )

            return ClaimResult(
                is_duplicate=True,
                fingerprint=fp,
                existing_tx_id=existing_tx_id,
                existing_status=existing_status,
                claimed_by=original_claimer,
            )

    # Fallback when Redis unavailable: Database check
    stmt = (
        select(IdempotencyKey)
        .where(
            IdempotencyKey.fingerprint == fp,
            IdempotencyKey.expires_at > now_utc,
        )
    )
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.duplicate_hits += 1
        await db.flush()
        return ClaimResult(
            is_duplicate=True,
            fingerprint=fp,
            existing_tx_id=existing.tx_id,
            existing_status=existing.status,
            claimed_by=existing.claimed_by,
        )

    ledger_entry = IdempotencyKey(
        fingerprint=fp,
        request_type=request_type,
        tx_id="PENDING",
        claimed_by=claimed_by,
        status=IdempotencyStatus.PENDING.value,
        claimed_at=now_utc,
        expires_at=expires_at,
        duplicate_hits=0,
    )
    db.add(ledger_entry)
    await db.flush()
    return ClaimResult(is_duplicate=False, fingerprint=fp)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FINALIZE (OUTCOME-BASED TTL POLICY)
# ─────────────────────────────────────────────────────────────────────────────

async def finalize_idempotency(
    redis_client: Optional[aioredis.Redis],
    db: AsyncSession,
    fingerprint: str,
    tx_id: str,
    final_status: str,
    rejection_grace_seconds: int = 2,
) -> None:
    """
    Applies the outcome-based dynamic TTL policy:
      • COMMITTED / DISPENSED / APPROVED -> Retains full TTL
      • REJECTED / FAILED -> Shortens TTL to 2-second grace window
      • ROLLED_BACK / EXPIRED -> Deletes Redis key immediately
    """
    now_utc = datetime.now(timezone.utc)
    status_upper = final_status.upper()
    redis_key_pattern = f"idem:*:{fingerprint}"

    # Update PostgreSQL Ledger
    ledger_stmt = (
        update(IdempotencyKey)
        .where(IdempotencyKey.fingerprint == fingerprint)
        .values(
            tx_id=tx_id,
            status=status_upper,
            resolved_at=now_utc,
        )
    )
    await db.execute(ledger_stmt)
    await db.flush()

    if not redis_client:
        return

    # Locate actual redis key
    keys = await redis_client.keys(redis_key_pattern)
    target_key = keys[0].decode("utf-8") if keys else None

    if not target_key:
        return

    try:
        if status_upper in ["COMMITTED", "DISPENSED", "APPROVED", "ACTIVE"]:
            # Keep Redis key with updated payload
            data = {"tx_id": tx_id, "status": status_upper, "resolved_at": now_utc.isoformat()}
            await redis_client.set(target_key, json.dumps(data), xx=True, keepttl=True)
        elif status_upper in ["REJECTED", "FAILED", "CONFLICT_LOSER"]:
            # Shorten to grace window (2s)
            data = {"tx_id": tx_id, "status": status_upper, "resolved_at": now_utc.isoformat()}
            await redis_client.set(target_key, json.dumps(data), ex=rejection_grace_seconds)
        elif status_upper in ["ROLLED_BACK", "EXPIRED", "ABORTED", "CANCELLED"]:
            # Delete key immediately
            await redis_client.delete(target_key)
    except Exception as e:
        logger.warning(f"Error applying outcome TTL policy to {target_key}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. PERIODIC RECONCILIATION
# ─────────────────────────────────────────────────────────────────────────────

async def reconcile_idempotency_keys(
    db: AsyncSession,
    redis_client: Optional[aioredis.Redis] = None,
    threshold_seconds: int = 60,
) -> int:
    """
    Periodic worker job: scans orphaned PENDING keys and reconciles them with
    actual transaction status or purges stale claims.
    """
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(seconds=threshold_seconds)

    stmt = (
        select(IdempotencyKey)
        .where(
            IdempotencyKey.status == IdempotencyStatus.PENDING.value,
            IdempotencyKey.claimed_at < cutoff,
        )
    )
    res = await db.execute(stmt)
    pending_keys = list(res.scalars().all())

    reconciled_count = 0
    for key in pending_keys:
        if key.tx_id and key.tx_id != "PENDING":
            tx = await db.get(Transaction, key.tx_id)
            if tx:
                tx_st = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
                await finalize_idempotency(redis_client, db, key.fingerprint, key.tx_id, tx_st)
                reconciled_count += 1
                continue

        # No transaction formed -> release key
        key.status = IdempotencyStatus.EXPIRED.value
        key.resolved_at = now_utc
        if redis_client:
            try:
                await redis_client.delete(f"idem:{key.request_type}:{key.fingerprint}")
            except Exception:
                pass
        reconciled_count += 1

    if reconciled_count:
        await db.flush()
        logger.info(f"Idempotency reconciliation: {reconciled_count} key(s) reconciled")

    return reconciled_count
