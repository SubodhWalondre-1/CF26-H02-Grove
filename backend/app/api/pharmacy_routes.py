"""
Pharmacy API routes — quantity-based resource management.

Separate router to keep existing routes.py untouched.
"""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_admin
from app.core.redis import get_redis
from app.models.models import User
from app.schemas.schemas import (
    PharmacyDispenseResponse,
    PharmacyReleaseResponse,
    PharmacyReservationResponse,
    PharmacyResourceCreateRequest,
    PharmacyResourceListResponse,
    PharmacyResourceResponse,
    PharmacyResourceUpdateRequest,
    PharmacyReserveRequest,
    PharmacyShortageListResponse,
)
from app.services.pharmacy import (
    InsufficientStockError,
    InvalidReservationStateError,
    PharmacyService,
)

router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])


def _resource_to_response(r) -> dict:
    """Convert a PharmacyResource ORM object to a response dict."""
    rt = r.resource_type.value if hasattr(r.resource_type, "value") else str(r.resource_type)
    st = r.status.value if hasattr(r.status, "value") else str(r.status)
    return {
        "id": str(r.id),
        "resource_type": rt,
        "sub_type": r.sub_type,
        "batch_id": r.batch_id,
        "total_quantity": r.total_quantity,
        "available_quantity": r.available_quantity,
        "reserved_quantity": r.reserved_quantity,
        "unit": r.unit,
        "expiry_date": str(r.expiry_date),
        "storage_location": r.storage_location,
        "critical_threshold": r.critical_threshold,
        "status": st,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


# =============================================================================
# LIST PHARMACY RESOURCES
# =============================================================================
@router.get(
    "/resources",
    response_model=PharmacyResourceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List pharmacy resources",
)
async def list_pharmacy_resources(
    resource_type: Optional[str] = Query(None, description="Filter by type"),
    sub_type: Optional[str] = Query(None, description="Filter by sub-type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = PharmacyService(db, redis)
    resources = await service.get_resources(
        resource_type=resource_type,
        sub_type=sub_type,
        status_filter=status_filter,
    )
    items = [_resource_to_response(r) for r in resources]
    return {"items": items, "total": len(items)}


# =============================================================================
# CREATE PHARMACY RESOURCE (Admin only)
# =============================================================================
@router.post(
    "/resources",
    response_model=PharmacyResourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: create/restock a pharmacy batch",
)
async def create_pharmacy_resource(
    payload: PharmacyResourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    service = PharmacyService(db, redis)
    try:
        expiry = date.fromisoformat(payload.expiry_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid expiry_date format. Use YYYY-MM-DD.",
        )
    resource = await service.create_resource({
        "resource_type": payload.resource_type,
        "sub_type": payload.sub_type,
        "batch_id": payload.batch_id,
        "total_quantity": payload.total_quantity,
        "unit": payload.unit,
        "expiry_date": expiry,
        "storage_location": payload.storage_location,
        "critical_threshold": payload.critical_threshold,
    })
    await db.commit()
    return _resource_to_response(resource)


# =============================================================================
# UPDATE PHARMACY RESOURCE (Admin only)
# =============================================================================
@router.patch(
    "/resources/{resource_id}",
    response_model=PharmacyResourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin: adjust threshold or recall batch",
)
async def update_pharmacy_resource(
    resource_id: str,
    payload: PharmacyResourceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    service = PharmacyService(db, redis)
    try:
        resource = await service.update_resource(
            resource_id=uuid.UUID(resource_id),
            updates=payload.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return _resource_to_response(resource)


# =============================================================================
# RESERVE QUANTITY
# =============================================================================
@router.post(
    "/reserve",
    response_model=PharmacyReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reserve pharmacy quantity for a transaction",
)
async def reserve_pharmacy_quantity(
    payload: PharmacyReserveRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = PharmacyService(db, redis)
    try:
        result = await service.reserve_quantity(
            resource_id=uuid.UUID(payload.resource_id),
            tx_id=payload.tx_id,
            quantity=payload.quantity,
            ttl_seconds=payload.ttl_seconds,
            is_emergency=payload.is_emergency,
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# DISPENSE RESERVATION
# =============================================================================
@router.post(
    "/reservations/{reservation_id}/dispense",
    response_model=PharmacyDispenseResponse,
    status_code=status.HTTP_200_OK,
    summary="Commit: mark reservation as dispensed",
)
async def dispense_pharmacy_reservation(
    reservation_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = PharmacyService(db, redis)
    try:
        result = await service.dispense_reservation(uuid.UUID(reservation_id))
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# RELEASE RESERVATION
# =============================================================================
@router.post(
    "/reservations/{reservation_id}/release",
    response_model=PharmacyReleaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Release a reservation (manual or TTL rollback)",
)
async def release_pharmacy_reservation(
    reservation_id: str,
    reason: str = Query(default="MANUAL", description="Release reason"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = PharmacyService(db, redis)
    try:
        result = await service.release_reservation(
            uuid.UUID(reservation_id), reason
        )
    except InvalidReservationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# SHORTAGE STATUS
# =============================================================================
@router.get(
    "/shortage-status",
    response_model=PharmacyShortageListResponse,
    status_code=status.HTTP_200_OK,
    summary="Current below-threshold pharmacy resources",
)
async def pharmacy_shortage_status(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = PharmacyService(db, redis)
    items = await service.get_shortage_status()
    return {"items": items, "total": len(items)}
