"""Shared pytest fixtures for the datagigbackend test suite."""
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings


# ---------------------------------------------------------------------------
# Mock settings fixture — overrides the real Settings singleton in tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> Settings:
    """Return a Settings instance with safe dummy values (no real secrets)."""
    return Settings(
        app_env="test",
        secret_key="test-secret-key",
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        database_url="postgresql://test:test@localhost:5432/test",
        resend_api_key="re_test_key",
        internal_api_secret="test-internal-secret",
    )


# ---------------------------------------------------------------------------
# ASGI test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(mock_settings: Settings) -> AsyncIterator[AsyncClient]:
    """
    AsyncClient wired directly to the ASGI app.
    The lifespan is NOT invoked here — startup side-effects (DB pool,
    JWKS fetch) are mocked so tests are fully isolated.
    """
    from app.config import get_settings
    from app.main import app

    # Override get_settings so all Depends(get_settings) calls use test values
    app.dependency_overrides[get_settings] = lambda: mock_settings

    # Patch lifespan state so the app doesn't try to connect to real services
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock().__aenter__.return_value)
    mock_pool.close = AsyncMock()
    app.state.db_pool = mock_pool
    app.state.jwks = {"keys": []}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()
