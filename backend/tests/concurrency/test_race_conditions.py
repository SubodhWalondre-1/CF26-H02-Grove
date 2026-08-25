import asyncio
import pytest
from conftest import auth_headers


# 1. Calling POST /complete and POST /cancel simultaneously on the same TX
#    — only one should succeed; the other should get 409 or 422
@pytest.mark.concurrency
async def test_simultaneous_complete_and_cancel(
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

    complete_coro = async_client.post(
        f"/api/v1/transactions/{tx_id}/complete",
        headers=auth_headers(doctor_token),
    )
    cancel_coro = async_client.post(
        f"/api/v1/transactions/{tx_id}/cancel",
        json={"reason": "race condition test"},
        headers=auth_headers(doctor_token),
    )

    results = await asyncio.gather(complete_coro, cancel_coro, return_exceptions=True)
    status_codes = [
        r.status_code if hasattr(r, "status_code") else 500 for r in results
    ]

    # At most one should succeed (200/202); the other should fail (409/422/400)
    success_count = sum(1 for s in status_codes if s in (200, 202))
    assert success_count <= 1, (
        f"Both complete and cancel succeeded simultaneously: {status_codes}"
    )


# 2. Calling POST /bundles/{tx_id}/commit twice simultaneously
#    — second call should be idempotent or return 409
@pytest.mark.concurrency
async def test_double_commit_is_safe(
    async_client, admin_token, doctor_token, seed_resources, seed_patient
):
    create_resp = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "care_bundle",
            "patient_id": seed_patient,
            "resource_ids": [seed_resources["ot"], seed_resources["surgeon"]],
        },
        headers=auth_headers(doctor_token),
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["tx_id"]

    commit1_coro = async_client.post(
        f"/api/v1/bundles/{tx_id}/commit",
        headers=auth_headers(admin_token),
    )
    commit2_coro = async_client.post(
        f"/api/v1/bundles/{tx_id}/commit",
        headers=auth_headers(admin_token),
    )

    results = await asyncio.gather(commit1_coro, commit2_coro, return_exceptions=True)
    codes = [r.status_code if hasattr(r, "status_code") else 500 for r in results]

    # At least one should succeed; the duplicate should return 409 or 200 (idempotent)
    assert any(c in (200, 409) for c in codes), (
        f"Unexpected codes on double commit: {codes}"
    )
    # Neither should be a 500
    assert all(c < 500 for c in codes), f"Server error on double commit: {codes}"


# 3. GET /resources — status stays consistent during high write concurrency
@pytest.mark.concurrency
async def test_resource_status_consistent_under_load(
    async_client, doctor_token, seed_resources, seed_patient
):
    """Fire 10 TXs and 10 GET /resources calls concurrently.
    The resource list should never 500, and status values should be valid enum values."""
    valid_statuses = {"available", "tentative", "locked", "maintenance"}

    tx_coros = [
        async_client.post(
            "/api/v1/transactions",
            json={
                "request_type": "single_resource",
                "patient_id": seed_patient,
                "resource_id": seed_resources["ot"],
            },
            headers=auth_headers(doctor_token),
        )
        for _ in range(10)
    ]
    read_coros = [
        async_client.get("/api/v1/resources", headers=auth_headers(doctor_token))
        for _ in range(10)
    ]

    all_results = await asyncio.gather(*tx_coros, *read_coros, return_exceptions=True)
    read_results = all_results[10:]  # second half are the reads

    for resp in read_results:
        if hasattr(resp, "status_code"):
            assert resp.status_code < 500
            if resp.status_code == 200:
                body = resp.json()
                items = body if isinstance(body, list) else body.get("items", [])
                for resource in items:
                    assert resource.get("status") in valid_statuses
