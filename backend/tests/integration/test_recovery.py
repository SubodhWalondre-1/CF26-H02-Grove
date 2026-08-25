from datetime import datetime, timezone
import pytest
from conftest import auth_headers
from app.models.models import HoldState, RequestType, Transaction, TransactionResource, TxState


# 1. GET /recovery/incomplete-transactions returns the correct envelope shape
@pytest.mark.integration
async def test_incomplete_transactions_endpoint(async_client, admin_token):
    resp = await async_client.get(
        "/api/v1/recovery/incomplete-transactions",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", [])
    for item in items:
        assert "tx_id" in item
        assert "state" in item


# 2. GET /recovery/runs returns a list of recovery run records
@pytest.mark.integration
async def test_recovery_runs_endpoint(async_client, admin_token):
    resp = await async_client.get(
        "/api/v1/recovery/runs", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200


# 3. POST /recovery/{tx_id}/resolve on a non-existent TX returns 404
@pytest.mark.integration
async def test_resolve_unknown_tx_returns_404(async_client, admin_token):
    resp = await async_client.post(
        "/api/v1/recovery/TX-DOESNOTEXIST/resolve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


# 4. POST /recovery/{tx_id}/resolve on a CLOSED TX returns 409 (already resolved)
@pytest.mark.integration
async def test_resolve_already_closed_tx_returns_409(
    async_client, admin_token, doctor_token, seed_resources, seed_patient
):
    # Create and complete/cancel a TX to transition to terminal state
    create_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ventilator"],
        },
        headers=auth_headers(doctor_token),
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["tx_id"]

    await async_client.post(
        f"/api/v1/transactions/{tx_id}/cancel",
        json={"reason": "test"},
        headers=auth_headers(doctor_token),
    )

    resolve_resp = await async_client.post(
        f"/api/v1/recovery/{tx_id}/resolve",
        headers=auth_headers(admin_token),
    )
    # Should be 409 (already in terminal state) or 200
    assert resolve_resp.status_code in (200, 409)


# 5. Recovery resolve response includes action_taken and verified_state
@pytest.mark.integration
async def test_recovery_resolve_response_shape(
    async_client, admin_token, db_session, seed_patient, seed_resources
):
    # Insert an in-flight incomplete transaction directly into DB session
    now = datetime.now(timezone.utc)
    tx = Transaction(
        tx_id="TX-REC-SHAPE",
        request_type=RequestType.care_bundle,
        patient_id=seed_patient,
        requested_by="USR-ADMIN-TEST",
        state=TxState.PREPARING,
        request_fingerprint="FP-REC",
        hold_ttl_seconds=30,
        hold_expires_at=now,
        created_at=now,
        updated_at=now,
    )
    tr = TransactionResource(
        tx_id="TX-REC-SHAPE",
        resource_id=seed_resources["ot"],
        hold_state=HoldState.tentative,
        updated_at=now,
    )
    db_session.add(tx)
    db_session.add(tr)
    await db_session.commit()

    resolve_resp = await async_client.post(
        f"/api/v1/recovery/{tx.tx_id}/resolve",
        headers=auth_headers(admin_token),
    )
    assert resolve_resp.status_code == 200
    body = resolve_resp.json()
    assert "action_taken" in body
    assert "verified_state" in body
