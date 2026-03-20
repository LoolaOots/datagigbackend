"""Tests for GET /profile endpoint."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.dependencies import get_current_user
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
AUTH_HEADERS = {"authorization": "Bearer fake-token"}


def override_current_user() -> dict:
    return {"sub": FAKE_USER_ID, "email": "test@example.com"}


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_no_auth(client: AsyncClient) -> None:
    """GET /profile without auth header returns 422."""
    response = await client.get("/profile")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_profile_success(client: AsyncClient) -> None:
    """GET /profile returns display_name and credits_balance_cents."""
    from app.models.profile import ProfileResponse

    profile = ProfileResponse(
        display_name="Jane Doe",
        credits_balance_cents=4200,
    )

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.profile_service.ProfileService.get_profile",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        response = await client.get("/profile", headers=AUTH_HEADERS)

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Jane Doe"
    assert body["credits_balance_cents"] == 4200


@pytest.mark.asyncio
async def test_get_profile_null_display_name(client: AsyncClient) -> None:
    """GET /profile returns null display_name when user has not set one."""
    from app.models.profile import ProfileResponse

    profile = ProfileResponse(
        display_name=None,
        credits_balance_cents=0,
    )

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.profile_service.ProfileService.get_profile",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        response = await client.get("/profile", headers=AUTH_HEADERS)

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] is None
    assert body["credits_balance_cents"] == 0


@pytest.mark.asyncio
async def test_get_profile_not_found(client: AsyncClient) -> None:
    """GET /profile returns 404 when user has no profile row."""
    from app.exceptions import NotFoundError

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.profile_service.ProfileService.get_profile",
        new_callable=AsyncMock,
        side_effect=NotFoundError(f"Profile for user {FAKE_USER_ID}"),
    ):
        response = await client.get("/profile", headers=AUTH_HEADERS)

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
