import pytest
from conftest import auth_headers, resolve_test_database_url
from app.core.security import decode_token


@pytest.mark.unit
def test_auth_headers_direct():
    token = "test.token.value"
    headers = auth_headers(token)
    assert headers == {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
def test_auth_headers_fixture(auth_headers_fixture):
    token = "test.token.fixture"
    headers = auth_headers_fixture(token)
    assert headers == {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
def test_resolve_test_database_url_logic(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://usr:pwd@host:5432/custom_test_db")
    assert resolve_test_database_url() == "postgresql+asyncpg://usr:pwd@host:5432/custom_test_db"

    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://usr:pwd@host:5432/mediora_db")
    assert resolve_test_database_url() == "postgresql+asyncpg://usr:pwd@host:5432/mediora_db_test"

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://usr:pwd@host:5432/mediora_db?ssl=true")
    assert resolve_test_database_url() == "postgresql+asyncpg://usr:pwd@host:5432/mediora_db_test?ssl=true"
