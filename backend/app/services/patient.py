from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Patient


async def get_patient(db: AsyncSession, patient_id: str) -> Patient:
    """
    Retrieves a patient record by ID.
    Raises HTTP 404 if the patient is not found.
    """
    stmt = select(Patient).where(Patient.patient_id == patient_id)
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found",
        )

    return patient


async def get_patient_acuity(db: AsyncSession, patient_id: str) -> Patient:
    """
    Retrieves the live, non-cached acuity metadata for a patient.
    Called directly during conflict arbitration.
    """
    return await get_patient(db=db, patient_id=patient_id)
