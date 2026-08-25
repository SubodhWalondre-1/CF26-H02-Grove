import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.main import app
from app.schemas.schemas import CreateTransactionRequest


@pytest.mark.unit
def test_seed_password_verification():
    seed_hash = "$2b$12$FJrPLJc8hfGbEgMqoDpoMeQ8YmVPg./wXwg7FSVyjvFfjYYuyeDSO"
    assert verify_password("mediora123", seed_hash) is True
    assert verify_password("wrongpassword", seed_hash) is False


@pytest.mark.unit
def test_password_hashing_roundtrip():
    plain = "secure_hospital_pass_2026"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong_password", hashed) is False


@pytest.mark.unit
def test_jwt_access_and_refresh_tokens():
    token_data = {"sub": "USR-1001", "username": "dr.mehta", "role": "doctor"}
    access_token = create_access_token(token_data)
    decoded_access = decode_token(access_token)
    assert decoded_access["sub"] == "USR-1001"
    assert decoded_access["role"] == "doctor"
    assert decoded_access["type"] == "access"

    refresh_token = create_refresh_token(token_data)
    decoded_refresh = decode_token(refresh_token)
    assert decoded_refresh["sub"] == "USR-1001"
    assert decoded_refresh["type"] == "refresh"


@pytest.mark.unit
def test_create_transaction_schema_validation():
    # Valid single resource
    single_req = CreateTransactionRequest(
        request_type="single_resource",
        patient_id="PT-0001",
        resource_id="RES-OT2",
    )
    assert single_req.resource_id == "RES-OT2"

    # Invalid single resource (missing resource_id)
    with pytest.raises(ValueError):
        CreateTransactionRequest(
            request_type="single_resource",
            patient_id="PT-0001",
        )

    # Valid care bundle
    bundle_req = CreateTransactionRequest(
        request_type="care_bundle",
        patient_id="PT-0001",
        resource_ids=["RES-OT2", "RES-SURG-A"],
    )
    assert len(bundle_req.resource_ids) == 2

    # Invalid care bundle (<2 resources)
    with pytest.raises(ValueError):
        CreateTransactionRequest(
            request_type="care_bundle",
            patient_id="PT-0001",
            resource_ids=["RES-OT2"],
        )


@pytest.mark.unit
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "mediora",
            "version": "1.0.0",
        }


@pytest.mark.unit
async def test_unauthorized_access_to_me_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
