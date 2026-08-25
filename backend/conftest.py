import asyncio
from decimal import Decimal
import os
from pathlib import Path
import sys
from typing import AsyncGenerator, Callable, Dict

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Set default test environment variables if not already defined
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://mediora:mediora_112_pass@localhost:5433/mediora_db",
)
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://mediora:mediora_112_pass@localhost:5433/mediora_test",
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "mediora_test_jwt_secret_key_2026_super_secure_hash"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.models import (
    AdminConfig,
    AdminPolicy,
    HoldState,
    Patient,
    Resource,
    ResourceStatus,
    ResourceType,
    User,
    UserRole,
)


def auth_headers(token: str) -> Dict[str, str]:
    """
    Constructs authorization header dictionary with the provided Bearer token.
    """
    return {"Authorization": f"Bearer {token}"}


auth_headers_helper = auth_headers


@pytest.fixture
def auth_headers_fixture() -> Callable[[str], Dict[str, str]]:
    """
    Pytest fixture wrapper around auth_headers helper function.
    """
    return auth_headers_helper


def resolve_test_database_url() -> str:
    """
    Resolves the async database connection URL for testing from environment variables.
    """
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        return test_url

    base_url = os.environ.get("DATABASE_URL")
    if base_url:
        return base_url.replace("mediora_db", "mediora_db_test")

    return "postgresql+asyncpg://mediora:mediora_112_pass@localhost:5433/mediora_test"


PG_ENUMS = [
    ("user_role", ("doctor", "nurse", "admin", "system")),
    ("resource_type", ("ot", "surgeon", "anesthesia", "ventilator")),
    ("resource_status", ("available", "tentative", "locked", "maintenance")),
    ("request_type", ("single_resource", "care_bundle")),
    (
        "tx_state",
        (
            "CREATED",
            "QUEUED",
            "ARBITRATING",
            "NO_CONFLICT",
            "PREPARING",
            "COMMITTING",
            "COMMITTED",
            "ACTIVE",
            "ROLLINGBACK",
            "ABORTED",
            "COMPLETED",
            "CANCELLED",
            "COMPENSATING",
            "RELEASED",
            "CLOSED",
        ),
    ),
    ("hold_state", ("requested", "tentative", "held", "released", "failed")),
    ("conflict_status", ("unresolved", "resolved")),
    ("bed_type_enum", ("ICU", "GENERAL", "STEP_DOWN", "EMERGENCY")),
    (
        "bed_status_enum",
        (
            "FREE",
            "CLEANING",
            "SANITIZED",
            "READY",
            "TENTATIVE_HOLD",
            "LOCKED",
            "IN_USE",
            "POST_USE",
            "MAINTENANCE",
            "OUT_OF_SERVICE",
        ),
    ),
    ("pharmacy_resource_type", ("MEDICATION_SLOT", "BLOOD_UNIT", "OXYGEN_UNIT")),
    ("pharmacy_resource_status", ("AVAILABLE", "RESERVED", "DISPENSED", "EXPIRED", "RECALLED")),
    ("pharmacy_reservation_status", ("PENDING", "CONFIRMED", "DISPENSED", "CANCELLED", "EXPIRED")),
    ("diagnostic_resource_type", ("DIAGNOSTIC_MRI", "DIAGNOSTIC_CT", "DIAGNOSTIC_XRAY", "LAB_SLOT")),
    ("equipment_status", ("AVAILABLE", "IN_USE", "MAINTENANCE", "CALIBRATING")),
    ("appointment_status", ("SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW")),
    ("lab_slot_status", ("AVAILABLE", "FULL", "MAINTENANCE")),
    ("sample_status", ("QUEUED", "PROCESSING", "COMPLETED", "REJECTED")),
    ("sample_priority", ("STAT", "URGENT", "ROUTINE")),
    ("transfer_status", ("PENDING", "IN_TRANSIT", "COMPLETED", "CANCELLED", "FAILED")),
    ("transfer_type", ("STEP_UP", "STEP_DOWN", "LATERAL", "EXTERNAL")),
    ("escalation_decision", ("APPROVED", "DENIED", "QUEUED")),
    ("escalation_source_feature", ("SINGLE_RESOURCE", "CARE_BUNDLE", "PATIENT_TRANSFER", "EMERGENCY_OVERRIDE_ROUTED", "MANUAL_ESCALATION")),
    ("idempotency_status", ("IN_PROGRESS", "COMMITTED", "REJECTED", "ROLLED_BACK")),
    ("override_trigger_type", ("AUTOMATIC_ACUITY", "MANUAL_DECLARATION")),
    ("override_flag_reason", ("FREQUENCY_ANOMALY", "ACUITY_DISCREPANCY", "UNJUSTIFIED_MANUAL")),
]


@pytest_asyncio.fixture(scope="session")
async def test_db():
    """
    Session-scoped test database engine fixture.
    Creates all tables at the start of the session and drops them at teardown.
    """
    test_db_url = resolve_test_database_url()
    engine = create_async_engine(
        test_db_url,
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            for enum_name, enum_values in PG_ENUMS:
                vals = ", ".join(f"'{v}'" for v in enum_values)
                await conn.execute(
                    text(
                        f"""
                        DO $$ BEGIN
                            CREATE TYPE {enum_name} AS ENUM ({vals});
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$;
                        """
                    )
                )
        await conn.run_sync(Base.metadata.create_all)

        # Baseline seed records
        await conn.execute(
            text(
                """
                INSERT INTO users (user_id, username, password_hash, role, display_name, created_at, is_active) VALUES
                ('USR-SYSTEM', 'system', 'NOT_A_REAL_HASH', 'system', 'System', NOW(), true),
                ('USR-DR-TEST', 'dr.test', '$2b$12$6/YQhUjQ0cI8.z.Kq4q7Z.P4NvZ4w1fH2iM8aJgQ7L6kF9oX3g7y2', 'doctor', 'Dr. Test', NOW(), true),
                ('USR-NURSE-TEST', 'nurse.test', '$2b$12$6/YQhUjQ0cI8.z.Kq4q7Z.P4NvZ4w1fH2iM8aJgQ7L6kF9oX3g7y2', 'nurse', 'Nurse Test', NOW(), true),
                ('USR-ADMIN-TEST', 'admin.test', '$2b$12$6/YQhUjQ0cI8.z.Kq4q7Z.P4NvZ4w1fH2iM8aJgQ7L6kF9oX3g7y2', 'admin', 'Admin Test', NOW(), true)
                ON CONFLICT (user_id) DO NOTHING
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO patients (patient_id, name, clinical_context, base_acuity, updated_at) VALUES
                ('PT-TEST', 'Test Patient', 'Post-op recovery observation', 6.00, NOW())
                ON CONFLICT (patient_id) DO NOTHING
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO resources (resource_id, type, label, status, criticality, version, updated_at) VALUES
                ('RES-OT2', 'ot', 'Operating Theater 2', 'available', 1.50, 0, NOW()),
                ('RES-SURG-A', 'surgeon', 'Surgeon Team A', 'available', 1.20, 0, NOW()),
                ('RES-ANES-A', 'anesthesia', 'Anesthesia Team A', 'available', 1.30, 0, NOW()),
                ('RES-VENT3', 'ventilator', 'Ventilator Unit 3', 'available', 1.80, 0, NOW())
                ON CONFLICT (resource_id) DO NOTHING
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO admin_config (key, value, updated_by, updated_at) VALUES
                ('hold_ttl_seconds', 30, 'USR-SYSTEM', NOW()),
                ('wait_coefficient_per_min', 0.12, 'USR-SYSTEM', NOW())
                ON CONFLICT (key) DO NOTHING
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO admin_policies (role, action, scope) VALUES
                ('doctor', 'single_resource', 'allowed'),
                ('doctor', 'care_bundle', 'allowed'),
                ('doctor', 'cancel', 'own_tx'),
                ('doctor', 'monitor', 'own_cases'),
                ('nurse', 'single_resource', 'allowed'),
                ('nurse', 'care_bundle', 'policy_based'),
                ('nurse', 'cancel', 'own_assigned'),
                ('nurse', 'monitor', 'assigned_cases'),
                ('admin', 'single_resource', 'operational'),
                ('admin', 'care_bundle', 'operational'),
                ('admin', 'cancel', 'authorized_tx'),
                ('admin', 'monitor', 'all'),
                ('system', 'single_resource', 'denied'),
                ('system', 'care_bundle', 'denied'),
                ('system', 'cancel', 'automatic_recovery'),
                ('system', 'monitor', 'all')
                ON CONFLICT (role, action) DO NOTHING
                """
            )
        )

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def reset_db_state(request, test_db):
    """
    Function-scoped autouse fixture to ensure clean database state between tests.
    Resets resources to 'available' and clears transactional history for DB-backed tests.
    """
    if "unit" in request.keywords:
        yield
        return

    yield
    async with test_db.begin() as conn:
        await conn.execute(text("UPDATE resources SET status = 'available', held_by_tx = NULL;"))
        await conn.execute(text("DELETE FROM compensation_events;"))
        await conn.execute(text("DELETE FROM conflict_transactions;"))
        await conn.execute(text("DELETE FROM audit_events;"))
        await conn.execute(text("DELETE FROM conflicts;"))
        await conn.execute(text("DELETE FROM transaction_state_history;"))
        await conn.execute(text("DELETE FROM transaction_resources;"))
        await conn.execute(text("DELETE FROM transactions;"))


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped database session fixture for direct DB queries in tests.
    """
    session_factory = async_sessionmaker(
        bind=test_db,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """
    Function-scoped AsyncClient fixture configured with ASGITransport and per-request get_db session.
    """
    session_factory = async_sessionmaker(
        bind=test_db,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def doctor_token() -> str:
    """
    Returns a signed Bearer JWT access token for dr.test doctor user.
    """
    token_data = {
        "sub": "USR-DR-TEST",
        "username": "dr.test",
        "role": "doctor",
    }
    return create_access_token(data=token_data)


@pytest.fixture
def nurse_token() -> str:
    """
    Returns a signed Bearer JWT access token for nurse.test nurse user.
    """
    token_data = {
        "sub": "USR-NURSE-TEST",
        "username": "nurse.test",
        "role": "nurse",
    }
    return create_access_token(data=token_data)


@pytest.fixture
def admin_token() -> str:
    """
    Returns a signed Bearer JWT access token for admin.test admin user.
    """
    token_data = {
        "sub": "USR-ADMIN-TEST",
        "username": "admin.test",
        "role": "admin",
    }
    return create_access_token(data=token_data)


@pytest.fixture
def seed_resources() -> Dict[str, str]:
    """
    Returns a mapping dict of keys to resource_ids.
    """
    return {
        "ot": "RES-OT2",
        "surgeon": "RES-SURG-A",
        "anesthesia": "RES-ANES-A",
        "ventilator": "RES-VENT3",
    }


@pytest.fixture
def seed_patient() -> str:
    """
    Returns the seeded patient_id 'PT-TEST'.
    """
    return "PT-TEST"


@pytest_asyncio.fixture(scope="function")
async def redis_client():
    """
    Function-scoped Redis client fixture for direct Redis access in tests.
    """
    import redis.asyncio as aioredis
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        yield client
    finally:
        try:
            await client.aclose()
        except Exception:
            pass

