import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.models import Bed, BedStatus, BedType, Resource, ResourceStatus, ResourceType, User, UserRole
from app.schemas.recommendation import PatientIntakeItem, RecommendationRequest
from app.api.recommendation_routes import generate_emergency_recommendations


@pytest.mark.asyncio
async def test_recommendation_endpoint_read_only_guarantee():
    """
    Asserts that calling the recommendation endpoint executes purely read-only queries
    and never calls db.add(), db.delete(), or db.commit().
    """
    mock_db = AsyncMock()

    # Mock empty live pool
    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [
        Resource(resource_id="RES-OT2", type=ResourceType.ot, label="OT-2", status=ResourceStatus.available),
        Resource(resource_id="RES-SURG-A", type=ResourceType.surgeon, label="SURG-A", status=ResourceStatus.available),
        Resource(resource_id="RES-ANES-A", type=ResourceType.anesthesia, label="ANES-A", status=ResourceStatus.available),
    ]
    mock_bed_exec = MagicMock()
    mock_bed_exec.scalars.return_value.all.return_value = [
        Bed(id="BED-ICU-01", bed_number="201", bed_type=BedType.ICU, status=BedStatus.READY, floor=2)
    ]
    mock_db.execute.side_effect = [mock_exec, mock_bed_exec]

    mock_user = User(user_id="USR-1001", username="dr.mehta", role=UserRole.doctor)

    payload = RecommendationRequest(
        patients=[
            PatientIntakeItem(
                patient_id="PT-0001",
                procedure_type="trauma_surgery",
                acuity_score=9.0,
                clinical_notes="Critical trauma",
            )
        ]
    )

    response = await generate_emergency_recommendations(
        payload=payload,
        db=mock_db,
        current_user=mock_user,
    )

    # 1. Successful response shape
    assert len(response.results) == 1
    assert response.results[0].patient_id == "PT-0001"
    assert len(response.results[0].recommendations) > 0

    # 2. Strict read-only guarantee: db mutating methods MUST NEVER be called
    mock_db.add.assert_not_called()
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()
