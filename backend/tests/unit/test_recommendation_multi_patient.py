import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.models import Bed, BedStatus, BedType, Resource, ResourceStatus, ResourceType
from app.schemas.recommendation import PatientIntakeItem
from app.services.recommendation import get_recommendations


@pytest.mark.asyncio
async def test_multi_patient_mass_casualty_greedy_dedup():
    """
    3 incoming patients:
      - Patient A (acuity 9.5)
      - Patient B (acuity 7.0)
      - Patient C (acuity 5.0)
    All need general admission bed. Only 2 ready beds exist.
    Higher acuity patients get provisioned first.
    Patient A gets Bed 1 (greedy_reserved=True).
    Patient B gets Bed 2 (greedy_reserved=True).
    Patient C gets fallback="no_ready_resources".
    """
    mock_db = AsyncMock()

    # Setup 2 ready beds in DB mock
    beds = [
        Bed(id="BED-101", bed_number="101", bed_type=BedType.GENERAL, status=BedStatus.READY, floor=1),
        Bed(id="BED-102", bed_number="102", bed_type=BedType.GENERAL, status=BedStatus.READY, floor=1),
    ]

    mock_res_exec = MagicMock()
    mock_res_exec.scalars.return_value.all.return_value = []

    mock_bed_exec = MagicMock()
    mock_bed_exec.scalars.return_value.all.return_value = beds

    # Database returns empty resources, 2 beds
    mock_db.execute.side_effect = [mock_res_exec, mock_bed_exec]

    # Input patients in random order (Patient B, Patient A, Patient C)
    patients = [
        PatientIntakeItem(patient_id="PT-B", procedure_type="general_admission", acuity_score=7.0),
        PatientIntakeItem(patient_id="PT-A", procedure_type="general_admission", acuity_score=9.5),
        PatientIntakeItem(patient_id="PT-C", procedure_type="general_admission", acuity_score=5.0),
    ]

    response = await get_recommendations(patients=patients, db=mock_db)

    # 1. Output must be sorted by acuity descending: PT-A (9.5), PT-B (7.0), PT-C (5.0)
    assert len(response.results) == 3
    assert response.results[0].patient_id == "PT-A"
    assert response.results[1].patient_id == "PT-B"
    assert response.results[2].patient_id == "PT-C"

    # 2. PT-A receives a recommendation and reserves BED-101 (or BED-102)
    rec_a = response.results[0]
    assert len(rec_a.recommendations) > 0
    assert rec_a.recommendations[0].greedy_reserved is True
    res_a_id = rec_a.recommendations[0].resources[0].resource_id

    # 3. PT-B receives the OTHER bed
    rec_b = response.results[1]
    assert len(rec_b.recommendations) > 0
    assert rec_b.recommendations[0].greedy_reserved is True
    res_b_id = rec_b.recommendations[0].resources[0].resource_id
    assert res_a_id != res_b_id

    # 4. PT-C has no ready resources left and triggers fallback
    rec_c = response.results[2]
    assert rec_c.fallback == "no_ready_resources"
    assert len(rec_c.recommendations) == 0
