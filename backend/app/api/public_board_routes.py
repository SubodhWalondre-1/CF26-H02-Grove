"""
Public Donation Board Routes — Feature #22: Live Resource & Donation Board

STRICT DATA ISOLATION:
This endpoint is COMPLETELY PUBLIC and UNAUTHENTICATED.
It must never require auth headers, session cookies, or tokens.
It MUST NEVER return any patient identifiers, clinical case notes, or clinician identities.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.shortage import get_active_alerts

router = APIRouter(prefix="/public/board", tags=["Public Donation Board"])


@router.get("/alerts", status_code=status.HTTP_200_OK)
async def get_public_shortage_alerts(
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns active consumable shortages for the public lobby donation board.
    Unauthenticated public endpoint with zero PHI.
    """
    return await get_active_alerts(db)
