import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.models.models import Transaction, User, UserRole, RequestType, TxState
from app.models.operation_record import OperationRecord
from app.api.records_routes import (
    download_operation_record_pdf,
    get_operation_record_status,
    regenerate_operation_record,
)


@pytest.mark.asyncio
async def test_records_rbac_access_control(tmp_path):
    """
    Asserts Role Permission Matrix for PDF Operation Records:
      - Admin: Always allowed.
      - Lead/Requester Doctor: Allowed.
      - Unrelated Doctor: Forbidden (403).
    """
    mock_db = AsyncMock()

    # Mock transaction requested by dr.mehta
    mock_tx = Transaction(
        tx_id="TX-100",
        request_type=RequestType.care_bundle,
        patient_id="PT-01",
        requested_by="USR-MEHTA",
        state=TxState.CLOSED,
        request_fingerprint="fp100",
    )

    pdf_file = tmp_path / "operation-record-TX-100.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test content")

    mock_rec = OperationRecord(
        tx_id="TX-100",
        file_path=str(pdf_file),
        status="GENERATED",
        audit_id="AUD-TX-100",
        generated_at=datetime.now(timezone.utc),
    )

    # 1. Requester Doctor Access -> Allowed
    doc_user = User(user_id="USR-MEHTA", username="dr.mehta", role=UserRole.doctor)

    mock_exec_tx = MagicMock()
    mock_exec_tx.scalar_one_or_none.return_value = mock_tx
    mock_exec_rec = MagicMock()
    mock_exec_rec.scalar_one_or_none.return_value = mock_rec

    mock_db.execute.side_effect = [mock_exec_tx, mock_exec_rec]

    resp = await download_operation_record_pdf(
        tx_id="TX-100",
        db=mock_db,
        current_user=doc_user,
    )
    assert resp.status_code == 200

    # 2. Unrelated Doctor Access -> 403 Forbidden
    other_doc = User(user_id="USR-KAPOOR", username="dr.kapoor", role=UserRole.doctor)
    mock_db.execute.side_effect = [mock_exec_tx]

    with pytest.raises(HTTPException) as exc:
        await download_operation_record_pdf(
            tx_id="TX-100",
            db=mock_db,
            current_user=other_doc,
        )
    assert exc.value.status_code == 403

    # 3. Admin Access -> Allowed without checking ownership
    admin_user = User(user_id="USR-ADMIN", username="admin.ops", role=UserRole.admin)
    mock_db.execute.side_effect = [mock_exec_rec]

    admin_resp = await download_operation_record_pdf(
        tx_id="TX-100",
        db=mock_db,
        current_user=admin_user,
    )
    assert admin_resp.status_code == 200


@pytest.mark.asyncio
async def test_records_status_endpoint():
    mock_db = AsyncMock()

    mock_tx = Transaction(
        tx_id="TX-200",
        request_type=RequestType.single_resource,
        patient_id="PT-02",
        requested_by="USR-ADMIN",
        state=TxState.CLOSED,
        request_fingerprint="fp200",
    )
    mock_rec = OperationRecord(
        tx_id="TX-200",
        file_path="storage/operation_records/operation-record-TX-200.pdf",
        status="GENERATED",
        audit_id="AUD-TX-200",
        generated_at=datetime.now(timezone.utc),
    )

    mock_exec_rec = MagicMock()
    mock_exec_rec.scalar_one_or_none.return_value = mock_rec
    mock_db.execute.return_value = mock_exec_rec

    admin_user = User(user_id="USR-ADMIN", username="admin.ops", role=UserRole.admin)
    status_resp = await get_operation_record_status(
        tx_id="TX-200",
        db=mock_db,
        current_user=admin_user,
    )

    assert status_resp["tx_id"] == "TX-200"
    assert status_resp["status"] == "GENERATED"
    assert status_resp["audit_id"] == "AUD-TX-200"
