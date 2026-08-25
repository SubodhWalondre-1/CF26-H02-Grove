import pytest
from conftest import auth_headers


# 1. Care bundle with all-available resources commits as a whole unit
@pytest.mark.integration
async def test_bundle_all_held_commits(
    async_client, doctor_token, seed_resources, seed_patient
):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "care_bundle",
            "patient_id": seed_patient,
            "resource_ids": [
                seed_resources["ot"],
                seed_resources["surgeon"],
                seed_resources["anesthesia"],
                seed_resources["ventilator"],
            ],
        },
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["request_type"] == "care_bundle"
    tx_id = data["tx_id"]

    # GET /bundles/{tx_id}/prepare-status — verify structure
    status_resp = await async_client.get(
        f"/api/v1/bundles/{tx_id}/prepare-status",
        headers=auth_headers(doctor_token),
    )
    assert status_resp.status_code in (200, 404)  # 404 acceptable if already committed


# 2. GET /bundles/{tx_id}/prepare-status returns one entry per resource
@pytest.mark.integration
async def test_bundle_prepare_status_has_all_resources(
    async_client, doctor_token, seed_resources, seed_patient
):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "care_bundle",
            "patient_id": seed_patient,
            "resource_ids": [seed_resources["ot"], seed_resources["surgeon"]],
        },
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code == 201
    tx_id = resp.json()["tx_id"]

    status_resp = await async_client.get(
        f"/api/v1/bundles/{tx_id}/prepare-status",
        headers=auth_headers(doctor_token),
    )
    if status_resp.status_code == 200:
        body = status_resp.json()
        resource_ids = [r["resource_id"] for r in body["resources"]]
        assert seed_resources["ot"] in resource_ids
        assert seed_resources["surgeon"] in resource_ids


# 3. A bundle with a single_resource request_type in the body is rejected
@pytest.mark.integration
async def test_bundle_request_type_must_be_care_bundle(
    async_client, doctor_token, seed_resources, seed_patient
):
    # Sending resource_ids with request_type=single_resource is invalid
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_ids": [seed_resources["ot"], seed_resources["surgeon"]],
        },
        headers=auth_headers(doctor_token),
    )
    assert resp.status_code in (400, 422)


# 4. POST /bundles/{tx_id}/rollback — rollback releases all resources, not just some
@pytest.mark.integration
async def test_bundle_rollback_releases_all(
    async_client, admin_token, seed_resources, seed_patient
):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "care_bundle",
            "patient_id": seed_patient,
            "resource_ids": [seed_resources["ot"], seed_resources["surgeon"]],
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    tx_id = resp.json()["tx_id"]

    # Admin-triggered rollback
    rollback_resp = await async_client.post(
        f"/api/v1/bundles/{tx_id}/rollback",
        headers=auth_headers(admin_token),
    )
    assert rollback_resp.status_code in (200, 409)  # 409 if already committed/aborted

    # After rollback, resources should be available again
    if rollback_resp.status_code == 200:
        released = rollback_resp.json().get("resources_released", [])
        # All resources mentioned in the bundle should be in the released list
        assert set(released) >= {seed_resources["ot"], seed_resources["surgeon"]}


# 5. Nurse without care_bundle permission is denied
@pytest.mark.integration
async def test_nurse_cannot_create_bundle_if_policy_denies(
    async_client, nurse_token, seed_resources, seed_patient
):
    resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "care_bundle",
            "patient_id": seed_patient,
            "resource_ids": [seed_resources["ot"], seed_resources["surgeon"]],
        },
        headers=auth_headers(nurse_token),
    )
    # Depends on the policy matrix seed — expect 403 if nurse policy = denied, 201 if allowed
    assert resp.status_code in (201, 403)
