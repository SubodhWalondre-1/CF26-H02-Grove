"""
Diagnostic Equipment Readiness Strategy — Feature #19 (Refactored from Feature #14)

Evaluates readiness for duration-bound equipment (MRI, CT, X-Ray) including
operational status and calibration requirements.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.readiness_strategies.base import ReadinessResult, ReadinessStrategy
from app.models.diagnostics import DiagnosticEquipment, EquipmentStatus


class DiagnosticReadinessStrategy:
    def base_state_applies(self) -> bool:
        return False

    async def is_ready(
        self,
        db: AsyncSession,
        resource_id: str,
        requested_quantity: Optional[int] = None,
        requested_window: Optional[Dict[str, Any]] = None,
    ) -> ReadinessResult:
        now_utc = datetime.now(timezone.utc)

        try:
            eq_uuid = uuid.UUID(resource_id)
            stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == eq_uuid)
        except ValueError:
            stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.equipment_code == resource_id)

        eq = (await db.execute(stmt)).scalar_one_or_none()
        if not eq:
            return ReadinessResult(
                is_ready=False,
                status="NOT_FOUND",
                reason=f"Diagnostic equipment '{resource_id}' not found",
            )

        if eq.status != EquipmentStatus.available:
            return ReadinessResult(
                is_ready=False,
                status=eq.status.value,
                reason=f"Diagnostic machine is in {eq.status.value} state",
                details={"equipment_code": eq.equipment_code, "resource_type": eq.resource_type.value},
            )

        if eq.calibration_due_at and eq.calibration_due_at < now_utc:
            return ReadinessResult(
                is_ready=False,
                status="CALIBRATION_OVERDUE",
                reason=f"Calibration expired on {eq.calibration_due_at.isoformat()}",
                details={"equipment_code": eq.equipment_code, "calibration_due_at": eq.calibration_due_at.isoformat()},
            )

        return ReadinessResult(
            is_ready=True,
            status="READY",
            details={
                "equipment_code": eq.equipment_code,
                "resource_type": eq.resource_type.value,
                "avg_scan_minutes": eq.avg_scan_minutes,
                "requires_contrast": eq.requires_contrast,
            },
        )
