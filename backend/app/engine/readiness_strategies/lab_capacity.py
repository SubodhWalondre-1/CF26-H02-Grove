"""
Lab Capacity Readiness Strategy — Feature #19 (Refactored from Feature #14)

Evaluates concurrent sample throughput and operational capacity for laboratory stations.
"""

from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.readiness_strategies.base import ReadinessResult, ReadinessStrategy
from app.models.diagnostics import LabSlot, LabSlotStatus


class LabCapacityReadinessStrategy:
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
            slot_uuid = uuid.UUID(resource_id)
            stmt = select(LabSlot).where(LabSlot.id == slot_uuid)
        except ValueError:
            stmt = select(LabSlot).where(LabSlot.lab_station_code == resource_id)

        slot = (await db.execute(stmt)).scalar_one_or_none()
        if not slot:
            return ReadinessResult(
                is_ready=False,
                status="NOT_FOUND",
                reason=f"Lab station '{resource_id}' not found",
            )

        if slot.status != LabSlotStatus.available:
            return ReadinessResult(
                is_ready=False,
                status=slot.status.value,
                reason=f"Lab station is in {slot.status.value} status",
                details={"lab_station_code": slot.lab_station_code},
            )

        req_qty = requested_quantity or 1
        if slot.current_load + req_qty > slot.max_concurrent:
            return ReadinessResult(
                is_ready=False,
                status="CAPACITY_EXCEEDED",
                reason=f"Station at capacity ({slot.current_load}/{slot.max_concurrent} samples processing)",
                details={
                    "lab_station_code": slot.lab_station_code,
                    "current_load": slot.current_load,
                    "max_concurrent": slot.max_concurrent,
                },
            )

        return ReadinessResult(
            is_ready=True,
            status="READY",
            details={
                "lab_station_code": slot.lab_station_code,
                "current_load": slot.current_load,
                "available_capacity": slot.max_concurrent - slot.current_load,
            },
        )
