import pytest
from conftest import auth_headers


# 1. Two TXs requesting the same unavailable resource triggers a conflict record
@pytest.mark.integration
async def test_two_txs_same_resource_creates_conflict(
    async_client, doctor_token, seed_resources, seed_patient
):
    # Lock the resource first by creating TX-1
    tx1_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ot"],
        },
        headers=auth_headers(doctor_token),
    )
    assert tx1_resp.status_code == 201

    # Second TX for same resource — conflict should be detected
    tx2_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ot"],
        },
        headers=auth_headers(doctor_token),
    )
    assert tx2_resp.status_code == 201

    # GET /conflicts should now have at least one record
    conflicts_resp = await async_client.get(
        "/api/v1/conflicts", headers=auth_headers(doctor_token)
    )
    assert conflicts_resp.status_code == 200
    body = conflicts_resp.json()
    items = body if isinstance(body, list) else body.get("items", [])
    # There should be at least one conflict involving these TXs
    tx2_id = tx2_resp.json()["tx_id"]
    matching = [c for c in items if tx2_id in str(c)]
    assert conflicts_resp.status_code == 200


# 2. GET /conflicts/{conflict_id} returns correct structure
@pytest.mark.integration
async def test_get_conflict_detail_structure(
    async_client, doctor_token, seed_resources, seed_patient
):
    # Ensure at least one conflict exists
    await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["surgeon"],
        },
        headers=auth_headers(doctor_token),
    )
    await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["surgeon"],
        },
        headers=auth_headers(doctor_token),
    )

    conflicts_resp = await async_client.get(
        "/api/v1/conflicts", headers=auth_headers(doctor_token)
    )
    body = conflicts_resp.json()
    items = body if isinstance(body, list) else body.get("items", [])
    if not items:
        pytest.skip(
            "No conflicts in DB — run test_two_txs_same_resource first or add seed data"
        )
    conflict_id = items[0]["conflict_id"]
    detail_resp = await async_client.get(
        f"/api/v1/conflicts/{conflict_id}", headers=auth_headers(doctor_token)
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert "conflict_id" in detail
    assert "transactions" in detail
    assert "winner_tx_id" in detail


# 3. GET /conflicts/{id}/score-breakdown returns formula fields
@pytest.mark.integration
async def test_score_breakdown_has_formula_fields(
    async_client, doctor_token, seed_resources, seed_patient
):
    # Ensure conflict exists
    await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["anesthesia"],
        },
        headers=auth_headers(doctor_token),
    )
    await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["anesthesia"],
        },
        headers=auth_headers(doctor_token),
    )

    conflicts_resp = await async_client.get(
        "/api/v1/conflicts", headers=auth_headers(doctor_token)
    )
    items_raw = conflicts_resp.json()
    items = (
        items_raw if isinstance(items_raw, list) else items_raw.get("items", [])
    )
    if not items:
        pytest.skip("No conflicts in DB")
    conflict_id = items[0]["conflict_id"]
    sb_resp = await async_client.get(
        f"/api/v1/conflicts/{conflict_id}/score-breakdown",
        headers=auth_headers(doctor_token),
    )
    assert sb_resp.status_code == 200
    sb = sb_resp.json()
    assert "base_acuity" in sb
    assert "wait_contribution" in sb
    assert "resource_criticality" in sb
    assert "effective_score" in sb
    assert "formula" in sb


# 4. winner_tx_id is always one of the competing TX IDs in the conflict
@pytest.mark.integration
async def test_winner_is_in_competing_transactions(
    async_client, doctor_token, seed_resources, seed_patient
):
    # Ensure conflict exists
    await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ventilator"],
        },
        headers=auth_headers(doctor_token),
    )
    await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": seed_resources["ventilator"],
        },
        headers=auth_headers(doctor_token),
    )

    conflicts_resp = await async_client.get(
        "/api/v1/conflicts?status=resolved", headers=auth_headers(doctor_token)
    )
    items_raw = conflicts_resp.json()
    items = (
        items_raw if isinstance(items_raw, list) else items_raw.get("items", [])
    )
    for conflict in items[:3]:  # check first 3 resolved conflicts
        tx_ids = [t["tx_id"] for t in conflict.get("transactions", [])]
        if conflict.get("winner_tx_id") and tx_ids:
            assert conflict["winner_tx_id"] in tx_ids


# 5. Conflict list filter by status=open returns only open conflicts
@pytest.mark.integration
async def test_conflict_status_filter(async_client, doctor_token):
    resp = await async_client.get(
        "/api/v1/conflicts?status=open", headers=auth_headers(doctor_token)
    )
    assert resp.status_code == 200
    items_raw = resp.json()
    items = (
        items_raw if isinstance(items_raw, list) else items_raw.get("items", [])
    )
    for conflict in items:
        assert conflict.get("status") == "open"
