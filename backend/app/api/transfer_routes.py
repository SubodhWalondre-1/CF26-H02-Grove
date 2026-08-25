"""
Patient Transfer API routes.

Separate router to keep existing routes untouched.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.redis import get_redis
from app.models.models import User
from app.schemas.schemas import (
    ActiveTransferListResponse,
    PatientTransferHistoryResponse,
    TransferCommitResponse,
    TransferInitiateRequest,
    TransferResponse,
    TransferRollbackResponse,
)
from app.services.transfer import (
    PreflightValidationError,
    TransferDestinationUnavailableError,
    TransferService,
    TransferTransportUnavailableError,
)

router = APIRouter(tags=["transfers"])


# =============================================================================
# 1. INITIATE PATIENT TRANSFER
# =============================================================================
@router.post(
    "/api/v1/transfers",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a patient transfer between beds",
)
async def initiate_transfer(
    payload: TransferInitiateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    try:
        result = await service.initiate_transfer(
            patient_id=payload.patient_id,
            source_bed_id=payload.source_bed_id,
            destination_bed_id=payload.destination_bed_id,
            transport_resource_id=payload.transport_resource_id,
            transfer_type=payload.transfer_type,
            reason=payload.reason,
            initiated_by=user.username,
            ttl_seconds=payload.ttl_seconds,
        )
    except PreflightValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PREFLIGHT_VALIDATION_FAILED", "message": str(e)},
        )
    except TransferDestinationUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DESTINATION_UNAVAILABLE", "message": str(e)},
        )
    except TransferTransportUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TRANSPORT_UNAVAILABLE", "message": str(e)},
        )

    await db.commit()
    return result


# =============================================================================
# 2. ACTIVE TRANSFERS (For Dashboard Widget)
# =============================================================================
@router.get(
    "/api/v1/transfers/active",
    response_model=ActiveTransferListResponse,
    status_code=status.HTTP_200_OK,
    summary="List currently active in-flight transfers",
)
async def get_active_transfers(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    items = await service.get_active_transfers()
    return {"items": items, "total": len(items)}


# =============================================================================
# 3. GET TRANSFER DETAIL BY TX_ID
# =============================================================================
@router.get(
    "/api/v1/transfers/{tx_id}",
    response_model=TransferResponse,
    status_code=status.HTTP_200_OK,
    summary="Get transfer status by transaction ID",
)
async def get_transfer_by_tx(
    tx_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    transfer = await service.get_transfer_by_tx(tx_id)
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transfer for TX {tx_id} not found",
        )
    return transfer


# =============================================================================
# 4. CONFIRM TRANSPORT (IN_TRANSIT)
# =============================================================================
@router.post(
    "/api/v1/transfers/{tx_id}/confirm-transport",
    status_code=status.HTTP_200_OK,
    summary="Mark transfer as IN_TRANSIT (patient departed source)",
)
async def confirm_transport(
    tx_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    try:
        result = await service.confirm_transport(tx_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 5. COMMIT TRANSFER (ARRIVED AT DESTINATION)
# =============================================================================
@router.post(
    "/api/v1/transfers/{tx_id}/commit",
    response_model=TransferCommitResponse,
    status_code=status.HTTP_200_OK,
    summary="Final commit on patient arrival at destination bed",
)
async def commit_transfer(
    tx_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    try:
        result = await service.commit_transfer(tx_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 6. CANCEL / ROLLBACK TRANSFER
# =============================================================================
@router.post(
    "/api/v1/transfers/{tx_id}/cancel",
    response_model=TransferRollbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel transfer and safely re-attach patient to source bed",
)
async def cancel_transfer(
    tx_id: str,
    reason: str = Query(default="MANUAL_CANCEL"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    try:
        result = await service.rollback_transfer(tx_id, reason=reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 7. PATIENT TRANSFER HISTORY
# =============================================================================
@router.get(
    "/api/v1/patients/{patient_id}/transfer-history",
    response_model=PatientTransferHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full bed movement history for a patient",
)
async def get_patient_transfer_history(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = TransferService(db, redis)
    items = await service.get_patient_transfer_history(patient_id)
    return {"items": items, "total": len(items)}
