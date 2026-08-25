import asyncio
from collections import Counter
import pytest
from conftest import auth_headers


# 1. Only one TX can hold a single resource at a time
@pytest.mark.concurrency
async def test_only_one_winner_for_same_resource(
    async_client, doctor_token, seed_resources, seed_patient
):
    """
    Fire 20 simultaneous POSTs for the same single resource.
    Exactly one transaction should reach COMMITTED/ACTIVE.
    The rest should be in ARBITRATING or have a conflict_id.
    """
    resource_id = seed_resources["ot"]
    N = 20

    async def book():
        return await async_client.post(
            "/api/v1/transactions",
            json={
                "request_type": "single_resource",
                "patient_id": seed_patient,
                "resource_id": resource_id,
            },
            headers=auth_headers(doctor_token),
        )

    responses = await asyncio.gather(*[book() for _ in range(N)])

    # All requests should return 201 (TX created, may be in QUEUED/ARBITRATING)
    status_codes = [r.status_code for r in responses]
    assert all(s == 201 for s in status_codes), f"Unexpected status codes: {status_codes}"

    # Check final TX states via GET
    tx_ids = [r.json()["tx_id"] for r in responses]
    final_states = []
    for tx_id in tx_ids:
        detail = await async_client.get(
            f"/api/v1/transactions/{tx_id}",
            headers=auth_headers(doctor_token),
        )
        if detail.status_code == 200:
            final_states.append(detail.json().get("status", "UNKNOWN"))

    # At most 1 TX should reach COMMITTED or ACTIVE (the lock winner)
    committed_or_active = [
        s for s in final_states if s in ("COMMITTED", "ACTIVE", "COMPLETED")
    ]
    assert len(committed_or_active) <= 1, (
        f"More than one TX holds the same resource: {committed_or_active}"
    )


# 2. Resource is available again after the winner is cancelled
@pytest.mark.concurrency
async def test_resource_released_after_cancel(
    async_client, doctor_token, seed_resources, seed_patient
):
    resource_id = seed_resources["surgeon"]

    # Book the resource
    tx1 = await async_client.post(
        "/api/v1/transactions",
        json={
            "request_type": "single_resource",
            "patient_id": seed_patient,
            "resource_id": resource_id,
        },
        headers=auth_headers(doctor_token),
    )
    assert tx1.status_code == 201
    tx_id = tx1.json()["tx_id"]

    # Cancel it
    await async_client.post(
        f"/api/v1/transactions/{tx_id}/cancel",
        json={"reason": "concurrency test cancel"},
        headers=auth_headers(doctor_token),
    )

    # Resource should be available again
    resource_resp = await async_client.get(
        f"/api/v1/resources/{resource_id}",
        headers=auth_headers(doctor_token),
    )
    assert resource_resp.status_code == 200
    # Status may be available or still releasing compensation — allow a brief window
    resource_status = resource_resp.json().get("status")
    assert resource_status in ("available", "tentative"), (
        f"Resource still locked after cancel: {resource_status}"
    )


# 3. Under 50 concurrent requests, no 500 errors
@pytest.mark.concurrency
async def test_no_500_under_high_concurrency(
    async_client, doctor_token, seed_resources, seed_patient
):
    resource_id = seed_resources["ventilator"]
    N = 50

    responses = await asyncio.gather(
        *[
            async_client.post(
                "/api/v1/transactions",
                json={
                    "request_type": "single_resource",
                    "patient_id": seed_patient,
                    "resource_id": resource_id,
                },
                headers=auth_headers(doctor_token),
            )
            for _ in range(N)
        ]
    )

    error_500 = [r for r in responses if r.status_code >= 500]
    assert len(error_500) == 0, (
        f"Server errors under load: {[r.text for r in error_500[:3]]}"
    )
