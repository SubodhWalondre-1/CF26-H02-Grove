"""
Discrete Readiness Strategy — Feature #19

Enforces canonical physical turnaround state machine for discrete physical units:
OT Rooms, ICU/General Beds, Surgeons, Ventilators.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.readiness_strategies.base import ReadinessResult, ReadinessStrategy
from app.models.models import Bed, BedStatus, Resource, ResourceStatus


class DiscreteReadinessStrategy:
    def base_state_applies(self) -> bool:
        return True

    async def is_ready(
        self,
        db: AsyncSession,
        resource_id: str,
        requested_quantity: Optional[int] = None,
        requested_window: Optional[Dict[str, Any]] = None,
    ) -> ReadinessResult:
        now_utc = datetime.now(timezone.utc)

        # 1. Check Beds table first
        bed_stmt = select(Bed).where(Bed.id == resource_id)
        bed = (await db.execute(bed_stmt)).scalar_one_or_none()

        if bed:
            if bed.status == BedStatus.READY:
                return ReadinessResult(
                    is_ready=True,
                    status=bed.status.value,
                    details={"bed_type": bed.bed_type.value, "floor": bed.floor, "room": bed.room_number},
                )
            elif bed.status == BedStatus.SANITIZED:
                return ReadinessResult(
                    is_ready=False,
                    status=bed.status.value,
                    reason="Awaiting manual verification / staff sign-off",
                    estimated_ready_at=bed.estimated_ready_at,
                    details={"bed_type": bed.bed_type.value, "requires_verification": True},
                )
            elif bed.status == BedStatus.CLEANING:
                return ReadinessResult(
                    is_ready=False,
                    status=bed.status.value,
                    reason="Currently undergoing cleaning & disinfection",
                    estimated_ready_at=bed.estimated_ready_at,
                    details={"bed_type": bed.bed_type.value},
                )
            elif bed.status == BedStatus.MAINTENANCE:
                return ReadinessResult(
                    is_ready=False,
                    status=bed.status.value,
                    reason=f"Under repair / maintenance: {bed.maintenance_reason or 'fault reported'}",
                    details={"bed_type": bed.bed_type.value},
                )
            else:
                return ReadinessResult(
                    is_ready=False,
                    status=bed.status.value,
                    reason=f"Bed is in {bed.status.value} state",
                    details={"bed_type": bed.bed_type.value},
                )

        # 2. Check Resource table
        res_stmt = select(Resource).where(Resource.resource_id == resource_id)
        resource = (await db.execute(res_stmt)).scalar_one_or_none()

        if not resource:
            return ReadinessResult(
                is_ready=False,
                status="NOT_FOUND",
                reason=f"Resource '{resource_id}' not found in registry",
            )

        if resource.status == ResourceStatus.available:
            return ReadinessResult(
                is_ready=True,
                status=resource.status.value,
                details={"resource_type": resource.type.value, "label": resource.label},
            )
        else:
            return ReadinessResult(
                is_ready=False,
                status=resource.status.value,
                reason=f"Resource is currently {resource.status.value}",
                estimated_ready_at=resource.estimated_ready_at,
                details={"resource_type": resource.type.value, "label": resource.label},
            )
