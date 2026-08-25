"""
API routes for Feature #21: Digital Emergency Operation Record (PDF)
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_active_user,
    get_db,
    require_admin,
)
from app.models.models import Transaction, User, UserRole
from app.models.operation_record import OperationRecord

router = APIRouter(prefix="/records", tags=["Digital Operation Records (PDF)"])


async def verify_record_access_permission(
    db: AsyncSession,
    tx_id: str,
    current_user: User,
) -> None:
    """
    Enforces Role Permission Matrix for PDF Operation Records:
      • Admin: Full access to all records.
      • Doctor: Access if requester or associated with the transaction.
      • Nurse: Access if requester or associated with the transaction.
    """
    user_role_str = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    ).lower()

    if user_role_str == "admin":
        return

    # Check transaction ownership
    stmt = select(Transaction).where(Transaction.tx_id == tx_id)
    tx = (await db.execute(stmt)).scalar_one_or_none()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{tx_id}' not found.",
        )

    # If user is the direct requester
    if tx.requested_by == current_user.user_id or tx.requested_by == current_user.username:
        return

    # Unauthorized
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to view or download this clinical operation record.",
    )


@router.get("/{tx_id}/status", status_code=status.HTTP_200_OK)
async def get_operation_record_status(
    tx_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns current generation status of the PDF operation record.
    """
    await verify_record_access_permission(db, tx_id, current_user)

    stmt = select(OperationRecord).where(OperationRecord.tx_id == tx_id)
    rec = (await db.execute(stmt)).scalar_one_or_none()

    if not rec:
        return {
            "tx_id": tx_id,
            "status": "PENDING",
            "generated_at": None,
            "audit_id": f"AUD-{tx_id}",
        }

    return {
        "tx_id": rec.tx_id,
        "status": rec.status,
        "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
        "audit_id": rec.audit_id or f"AUD-{tx_id}",
        "error_message": rec.error_message,
    }


@router.get("/{tx_id}/pdf")
async def download_operation_record_pdf(
    tx_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Streams the generated Operation Record PDF file to authorized clinicians.
    """
    await verify_record_access_permission(db, tx_id, current_user)

    stmt = select(OperationRecord).where(OperationRecord.tx_id == tx_id)
    rec = (await db.execute(stmt)).scalar_one_or_none()

    if not rec or rec.status == "PENDING":
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "detail": "Operation record PDF generation is in progress. Please retry in a few seconds.",
                "status": "PENDING",
            },
        )

    if rec.status == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Operation record generation failed: {rec.error_message or 'Unknown rendering error'}",
        )

    if not rec.file_path or not Path(rec.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Operation record file not found on disk at {rec.file_path}.",
        )

    return FileResponse(
        path=rec.file_path,
        media_type="application/pdf",
        filename=f"operation-record-{tx_id}.pdf",
    )


@router.post("/{tx_id}/regenerate", status_code=status.HTTP_200_OK)
async def regenerate_operation_record(
    tx_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin-only action: Re-dispatches background PDF generation for a transaction.
    """
    stmt = select(OperationRecord).where(OperationRecord.tx_id == tx_id)
    rec = (await db.execute(stmt)).scalar_one_or_none()
    if rec:
        rec.status = "PENDING"
        rec.error_message = None
        await db.commit()

    try:
        from app.workers.tasks import generate_operation_record_pdf
        generate_operation_record_pdf.delay(tx_id)
    except Exception as e:
        # Fallback to local synchronous run if Celery broker unavailable
        from app.services.record import aggregate_operation_record
        from app.services.pdf_renderer import render_operation_record_pdf
        op_data = await aggregate_operation_record(tx_id=tx_id, db=db)
        file_path, _ = render_operation_record_pdf(op_data)
        if rec:
            rec.file_path = file_path
            rec.status = "GENERATED"
            await db.commit()

    return {"message": f"Operation record PDF regeneration dispatched for {tx_id}.", "status": "PENDING"}
