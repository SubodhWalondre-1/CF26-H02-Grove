"""
Pharmacy Readiness Strategy — Feature #19 (Refactored from Feature #13)

Evaluates readiness for consumable / quantity-based pharmacy resources
(Medications, Blood Units, Oxygen).
"""

from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.readiness_strategies.base import ReadinessResult, ReadinessStrategy
from app.models.pharmacy import PharmacyResource, PharmacyResourceStatus


class PharmacyReadinessStrategy:
    def base_state_applies(self) -> bool:
        return False

    async def is_ready(
        self,
        db: AsyncSession,
        resource_id: str,
        requested_quantity: Optional[int] = None,
        requested_window: Optional[Dict[str, Any]] = None,
    ) -> ReadinessResult:
        try:
            res_uuid = uuid.UUID(resource_id)
            stmt = select(PharmacyResource).where(PharmacyResource.id == res_uuid)
        except ValueError:
            stmt = select(PharmacyResource).where(PharmacyResource.item_code == resource_id)

        res = (await db.execute(stmt)).scalar_one_or_none()
        if not res:
            return ReadinessResult(
                is_ready=False,
                status="NOT_FOUND",
                reason=f"Pharmacy resource '{resource_id}' not found",
            )

        if res.status != PharmacyResourceStatus.available:
            return ReadinessResult(
                is_ready=False,
                status=res.status.value,
                reason=f"Pharmacy stock is in {res.status.value} state (e.g. expired or recalled)",
                details={"item_code": res.item_code, "batch_number": res.batch_number},
            )

        req_qty = requested_quantity or 1
        if res.available_quantity < req_qty:
            return ReadinessResult(
                is_ready=False,
                status="INSUFFICIENT_STOCK",
                reason=f"Requested {req_qty} {res.unit_of_measure}, but only {res.available_quantity} available",
                details={
                    "item_code": res.item_code,
                    "available_quantity": res.available_quantity,
                    "requested_quantity": req_qty,
                },
            )

        return ReadinessResult(
            is_ready=True,
            status="READY",
            details={
                "item_code": res.item_code,
                "available_quantity": res.available_quantity,
                "batch_number": res.batch_number,
                "expiry_date": res.expiry_date.isoformat(),
            },
        )
