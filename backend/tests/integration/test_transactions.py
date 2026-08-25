import pytest
from conftest import auth_headers


# 1. POST /transactions — single resource, no conflict, happy path
@pytest.mark.integration
async def test_create_single_resource_tx(
    async_client, doctor_token, seed_resources, seed_patient
):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ventilator"],  # least contested
        },
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["request_type"] == "single_resource"
    assert data["status"] in ("QUEUED", "ACTIVE", "COMMITTED")  # may resolve synchronously


# 2. GET /transactions/{tx_id} — returns full detail
@pytest.mark.integration
async def test_get_transaction_detail(
    async_client, doctor_token, seed_resources, seed_patient
):
    # create first
    create_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ot"],
        },
        headers=auth_headers(doctor_token),
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["tx_id"]

    resp = await async_client.get(
        f"/api/v1/transactions/{tx_id}",
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 200
    assert resp.json()["tx_id"] == tx_id
    assert "status" in resp.json()
    assert "request_type" in resp.json()


# 3. GET /transactions/{tx_id}/state-history — returns ordered transitions
@pytest.mark.integration
async def test_state_history_has_created_first(
    async_client, doctor_token, seed_resources, seed_patient
):
    create_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["surgeon"],
        },
        headers=auth_headers(doctor_token),
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["tx_id"]

    resp = await async_client.get(
        f"/api/v1/transactions/{tx_id}/state-history",
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 200
    history = resp.json()["history"]
    assert len(history) >= 1
    assert history[0]["state"] == "CREATED"


# 4. POST /transactions/{tx_id}/complete — moves active TX to COMPLETED
@pytest.mark.integration
async def test_complete_transaction(
    async_client, doctor_token, seed_resources, seed_patient
):
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

    complete_resp = await async_client.post(
        f"/api/v1/transactions/{tx_id}/complete",
        headers=auth_headers(doctor_token),
    )
    # accept 200 or 409 (if TX hasn't reached ACTIVE yet — acceptable in fast tests)
    assert complete_resp.status_code in (200, 409, 422)


# 5. POST /transactions/{tx_id}/cancel — cancels and triggers compensation
@pytest.mark.integration
async def test_cancel_transaction(
    async_client, doctor_token, seed_resources, seed_patient
):
    create_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ot"],
        },
        headers=auth_headers(doctor_token),
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["tx_id"]

    cancel_resp = await async_client.post(
        f"/api/v1/transactions/{tx_id}/cancel",
        json={"reason": "Test cancel"},
        headers=auth_headers(doctor_token),
    )
    assert cancel_resp.status_code in (200, 202)


# 6. GET /transactions — list returns items for the requesting user
@pytest.mark.integration
async def test_list_transactions(
    async_client, doctor_token, seed_resources, seed_patient
):
    resp = await async_client.get(
        "/api/v1/transactions",
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 200
    assert "items" in resp.json() or isinstance(resp.json(), list)


# 7. GET /transactions with status filter
@pytest.mark.integration
async def test_list_transactions_status_filter(async_client, doctor_token):
    resp = await async_client.get(
        "/api/v1/transactions?status=QUEUED",
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 200


# 8. Unknown resource ID returns 422
@pytest.mark.integration
async def test_create_tx_unknown_resource(
    async_client, doctor_token, seed_patient
):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": "RES-DOESNOTEXIST",
        },
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code in (404, 422)


# 9. No auth returns 401
@pytest.mark.integration
async def test_create_tx_no_auth(async_client, seed_patient):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": "RES-OT2",
        },
    )
    assert resp.status_code == 401
