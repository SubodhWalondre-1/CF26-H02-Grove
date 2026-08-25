"""
API routes for Feature #20: AI Emergency Resource Recommendation Engine
"""

import logging
import time
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models.models import User
from app.schemas.recommendation import (
    PatientRecommendation,
    RecommendationRequest,
    RecommendationResponse,
)
from app.services.recommendation import get_recommendations

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Emergency Resource Recommendation Engine"])


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_emergency_recommendations(
    payload: RecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RecommendationResponse:
    """
    Evaluates required resources for incoming single or mass-casualty patient intake,
    scores live ready resources, and returns ranked top-3 explainable bundle options.

    Strictly read-only: never mutates resources or creates locks.
    """
    start_time = time.perf_counter()
    user_id = getattr(current_user, "username", None) or current_user.user_id

    try:
        response = await get_recommendations(patients=payload.patients, db=db)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        patient_ids = [p.patient_id for p in payload.patients]
        logger.info(
            f"Recommendation generated for patients={patient_ids} in {elapsed_ms:.1f}ms by user={user_id}"
        )

        return response

    except Exception as e:
        logger.error(f"Recommendation engine exception: {e}", exc_info=True)
        # Graceful degradation fallback
        fallback_results: List[PatientRecommendation] = [
            PatientRecommendation(
                patient_id=p.patient_id,
                procedure_type=p.procedure_type,
                acuity_score=p.acuity_score,
                recommendations=[],
                fallback="engine_unavailable",
                nearest_eta_minutes=15,
                partial_options=False,
            )
            for p in payload.patients
        ]
        return RecommendationResponse(results=fallback_results)
