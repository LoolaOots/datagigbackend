"""Tests for auth endpoints: POST /auth/otp/send, /otp/verify, /apple, /refresh."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.exceptions import AuthError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_override(mock_conn: Any):
    """Return an async generator dependency override that yields mock_conn."""

    async def _override() -> AsyncIterator[Any]:
        yield mock_conn

    return _override


# ---------------------------------------------------------------------------
# POST /auth/otp/send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_send_success(client: AsyncClient) -> None:
    """POST /auth/otp/send should return 200 and message='OTP sent'."""
    with patch(
        "app.services.auth_service._send_otp_sync",
        return_value=None,
    ):
        response = await client.post(
            "/auth/otp/send",
            json={"email": "user@example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "OTP sent"}


@pytest.mark.asyncio
async def test_otp_send_invalid_email(client: AsyncClient) -> None:
    """POST /auth/otp/send with invalid email should return 422."""
    response = await client.post(
        "/auth/otp/send",
        json={"email": "not-an-email"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_otp_send_extra_fields_rejected(client: AsyncClient) -> None:
    """POST /auth/otp/send with extra fields should return 422 (extra='forbid')."""
    response = await client.post(
        "/auth/otp/send",
        json={"email": "user@example.com", "extra_field": "bad"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_otp_send_supabase_failure(client: AsyncClient) -> None:
    """POST /auth/otp/send should return 401 when Supabase raises an error."""
    with patch(
        "app.services.auth_service._send_otp_sync",
        side_effect=Exception("Supabase error"),
    ):
        response = await client.post(
            "/auth/otp/send",
            json={"email": "user@example.com"},
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/otp/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_verify_success_new_user(client: AsyncClient) -> None:
    """POST /auth/otp/verify — new user: verifies OTP, creates user rows, returns tokens."""
    verify_result = {
        "access_token": "access-abc",
        "refresh_token": "refresh-abc",
        "user_id": "user-uuid-001",
        "email": "user@example.com",
    }

    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None  # user does not exist yet
    mock_conn.execute = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.auth_service._verify_otp_sync",
        return_value=verify_result,
    ):
        response = await client.post(
            "/auth/otp/verify",
            json={"email": "user@example.com", "token": "482917"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "access-abc"
    assert body["refresh_token"] == "refresh-abc"
    assert body["user_id"] == "user-uuid-001"


@pytest.mark.asyncio
async def test_otp_verify_existing_user(client: AsyncClient) -> None:
    """POST /auth/otp/verify — existing user: verifies OTP, skips row creation."""
    verify_result = {
        "access_token": "access-xyz",
        "refresh_token": "refresh-xyz",
        "user_id": "user-uuid-002",
        "email": "existing@example.com",
    }

    existing_row = {"id": "user-uuid-002"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = existing_row

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.auth_service._verify_otp_sync",
        return_value=verify_result,
    ):
        response = await client.post(
            "/auth/otp/verify",
            json={"email": "existing@example.com", "token": "123456"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["user_id"] == "user-uuid-002"
    # execute should NOT have been called since user already exists
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_otp_verify_bad_token(client: AsyncClient) -> None:
    """POST /auth/otp/verify — wrong OTP should return 401."""
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.auth_service._verify_otp_sync",
        side_effect=AuthError("OTP verification failed"),
    ):
        response = await client.post(
            "/auth/otp/verify",
            json={"email": "user@example.com", "token": "000000"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/apple
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_sign_in_success(client: AsyncClient) -> None:
    """POST /auth/apple — valid identity token returns tokens and creates user."""
    apple_result = {
        "access_token": "apple-access",
        "refresh_token": "apple-refresh",
        "user_id": "apple-user-uuid",
        "email": "apple@example.com",
    }

    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None  # first sign-in
    mock_conn.execute = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.auth_service._sign_in_apple_sync",
        return_value=apple_result,
    ):
        response = await client.post(
            "/auth/apple",
            json={"identity_token": "fake.apple.jwt"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "apple-access"
    assert body["user_id"] == "apple-user-uuid"


@pytest.mark.asyncio
async def test_apple_sign_in_failure(client: AsyncClient) -> None:
    """POST /auth/apple — invalid token should return 401."""
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.auth_service._sign_in_apple_sync",
        side_effect=AuthError("Apple sign-in failed"),
    ):
        response = await client.post(
            "/auth/apple",
            json={"identity_token": "invalid.token"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_apple_sign_in_extra_fields_rejected(client: AsyncClient) -> None:
    """POST /auth/apple with extra fields should return 422."""
    response = await client.post(
        "/auth/apple",
        json={"identity_token": "fake.jwt", "unexpected": "field"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient) -> None:
    """POST /auth/refresh — valid refresh token returns new tokens."""
    refresh_result = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
    }

    with patch(
        "app.services.auth_service._refresh_session_sync",
        return_value=refresh_result,
    ):
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": "old-refresh-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "new-access-token"
    assert body["refresh_token"] == "new-refresh-token"


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient) -> None:
    """POST /auth/refresh — expired/invalid refresh token should return 401."""
    with patch(
        "app.services.auth_service._refresh_session_sync",
        side_effect=AuthError("Token refresh failed"),
    ):
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": "expired-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_extra_fields_rejected(client: AsyncClient) -> None:
    """POST /auth/refresh with extra fields should return 422."""
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": "some-token", "extra": "bad"},
    )
    assert response.status_code == 422
