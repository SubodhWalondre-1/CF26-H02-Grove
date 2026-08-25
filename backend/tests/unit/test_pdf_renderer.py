import os
from pathlib import Path
from app.services.record import OperationRecordData
from app.services.pdf_renderer import render_operation_record_pdf, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename("TX-1001") == "operation-record-TX-1001.pdf"
    assert sanitize_filename("../../../etc/passwd") == "operation-record-etcpasswd.pdf"


def test_pdf_rendering_success(tmp_path):
    data = OperationRecordData(
        tx_id="TX-TEST-001",
        closed_at="2026-08-25 07:00:00 UTC",
        patient={
            "patient_id": "PT-01",
            "name": "Jane Smith",
            "procedure_type": "Trauma Surgery",
            "acuity_score": 9.2,
            "criticality_label": "CRITICAL",
        },
        medical_team=[
            {"employee_id": "dr.mehta", "name": "Dr. Ananya Mehta", "role": "Lead Surgeon"},
            {"employee_id": "nurse.priya", "name": "Nurse Priya", "role": "Nurse Specialist"},
        ],
        resources=[
            {"resource_id": "RES-OT-2", "type": "OT", "label": "OT Room 2", "final_status": "COMMITTED"},
            {"resource_id": "RES-SURG-A", "type": "SURGEON", "label": "Surgeon A", "final_status": "COMMITTED"},
        ],
        timeline=[
            {"timestamp": "2026-08-25 06:30:00", "event": "TX_CREATED", "actor": "dr.mehta", "decision": "SUCCESS"},
            {"timestamp": "2026-08-25 07:00:00", "event": "TX_COMMITTED", "actor": "system", "decision": "COMMITTED"},
        ],
        status="COMPLETED",
        audit_id="AUD-TX-TEST-001",
        arbiter_notes="No conflict detected.",
    )

    file_path, pdf_bytes = render_operation_record_pdf(data, output_dir=tmp_path)

    # 1. Output file exists
    assert os.path.exists(file_path)

    # 2. Starts with PDF magic header
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500
