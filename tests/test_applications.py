"""Tests for POST/GET /applications endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.dependencies import get_current_user
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_GIG_ID = "11111111-2222-3333-4444-555555555555"
FAKE_APP_ID = "66666666-7777-8888-9999-aaaaaaaaaaaa"
FAKE_APPLIED_AT = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

AUTH_HEADERS = {"authorization": "Bearer fake-token"}


def override_current_user() -> dict:
    return {"sub": FAKE_USER_ID, "email": "test@example.com"}


# ---------------------------------------------------------------------------
# POST /applications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_application_no_auth(client: AsyncClient) -> None:
    """POST /applications without auth header should return 422."""
    response = await client.post(
        "/applications",
        json={"gig_id": FAKE_GIG_ID, "device_type": "generic_ios"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_application_success(client: AsyncClient) -> None:
    """POST /applications with valid data returns 201 and application summary."""
    from app.models.applications import ApplicationCreatedResponse

    expected = ApplicationCreatedResponse(
        id=FAKE_APP_ID,
        gig_id=FAKE_GIG_ID,
        status="pending",
        applied_at=FAKE_APPLIED_AT,
    )

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.create_application",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        response = await client.post(
            "/applications",
            json={"gig_id": FAKE_GIG_ID, "device_type": "generic_ios"},
            headers=AUTH_HEADERS,
        )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == FAKE_APP_ID
    assert body["gig_id"] == FAKE_GIG_ID
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_create_application_note_too_long(client: AsyncClient) -> None:
    """POST /applications with note_from_user > 500 chars should return 422."""
    app.dependency_overrides[get_current_user] = override_current_user

    response = await client.post(
        "/applications",
        json={
            "gig_id": FAKE_GIG_ID,
            "device_type": "generic_ios",
            "note_from_user": "x" * 501,
        },
        headers=AUTH_HEADERS,
    )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_application_gig_not_open(client: AsyncClient) -> None:
    """POST /applications when gig is not open returns 400."""
    from app.exceptions import AppError

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.create_application",
        new_callable=AsyncMock,
        side_effect=AppError("Gig is not open for applications", status_code=400),
    ):
        response = await client.post(
            "/applications",
            json={"gig_id": FAKE_GIG_ID, "device_type": "generic_ios"},
            headers=AUTH_HEADERS,
        )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400
    assert "not open" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_application_device_not_allowed(client: AsyncClient) -> None:
    """POST /applications with unsupported device type returns 400."""
    from app.exceptions import AppError

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.create_application",
        new_callable=AsyncMock,
        side_effect=AppError("Device type 'apple_watch' is not accepted for this gig", status_code=400),
    ):
        response = await client.post(
            "/applications",
            json={"gig_id": FAKE_GIG_ID, "device_type": "apple_watch"},
            headers=AUTH_HEADERS,
        )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_application_already_applied(client: AsyncClient) -> None:
    """POST /applications when already applied returns 409."""
    from app.exceptions import AppError

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.create_application",
        new_callable=AsyncMock,
        side_effect=AppError("You have already applied to this gig", status_code=409),
    ):
        response = await client.post(
            "/applications",
            json={"gig_id": FAKE_GIG_ID, "device_type": "generic_ios"},
            headers=AUTH_HEADERS,
        )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_application_extra_fields_rejected(client: AsyncClient) -> None:
    """POST /applications with unknown fields should return 422 (extra='forbid')."""
    app.dependency_overrides[get_current_user] = override_current_user

    response = await client.post(
        "/applications",
        json={"gig_id": FAKE_GIG_ID, "device_type": "generic_ios", "unknown_field": "bad"},
        headers=AUTH_HEADERS,
    )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /applications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_applications_no_auth(client: AsyncClient) -> None:
    """GET /applications without auth returns 422."""
    response = await client.get("/applications")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_applications_success(client: AsyncClient) -> None:
    """GET /applications returns a list of applications for the current user."""
    from app.models.applications import ApplicationListItem

    items = [
        ApplicationListItem(
            id=FAKE_APP_ID,
            gig_id=FAKE_GIG_ID,
            gig_title="My Gig",
            status="pending",
            device_type="generic_ios",
            assignment_code=None,
            applied_at=FAKE_APPLIED_AT,
            note_from_company=None,
        )
    ]

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.list_applications",
        new_callable=AsyncMock,
        return_value=items,
    ):
        response = await client.get("/applications", headers=AUTH_HEADERS)

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == FAKE_APP_ID
    assert body[0]["gig_title"] == "My Gig"
    assert body[0]["assignment_code"] is None


@pytest.mark.asyncio
async def test_list_applications_empty(client: AsyncClient) -> None:
    """GET /applications returns empty list when user has no applications."""
    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.list_applications",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = await client.get("/applications", headers=AUTH_HEADERS)

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /applications/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_application_no_auth(client: AsyncClient) -> None:
    """GET /applications/{id} without auth returns 422."""
    response = await client.get(f"/applications/{FAKE_APP_ID}")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_application_success(client: AsyncClient) -> None:
    """GET /applications/{id} returns full detail including gig labels."""
    from app.models.applications import (
        ApplicationDetailResponse,
        ApplicationGigDetail,
        ApplicationLabelDetail,
    )

    detail = ApplicationDetailResponse(
        id=FAKE_APP_ID,
        gig_id=FAKE_GIG_ID,
        gig_title="My Gig",
        status="accepted",
        device_type="generic_ios",
        assignment_code="ABC123",
        applied_at=FAKE_APPLIED_AT,
        note_from_company="Good profile",
        note_from_user="I have experience",
        gig_detail=ApplicationGigDetail(
            title="My Gig",
            description="Walk around",
            activity_type="walking",
            data_deadline=None,
            labels=[
                ApplicationLabelDetail(
                    id="label-uuid-1",
                    label_name="walking",
                    duration_seconds=120,
                    rate_cents=500,
                )
            ],
        ),
    )

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.get_application",
        new_callable=AsyncMock,
        return_value=detail,
    ):
        response = await client.get(
            f"/applications/{FAKE_APP_ID}", headers=AUTH_HEADERS
        )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == FAKE_APP_ID
    assert body["assignment_code"] == "ABC123"
    assert body["note_from_user"] == "I have experience"
    assert "gig_detail" in body
    assert len(body["gig_detail"]["labels"]) == 1
    assert body["gig_detail"]["labels"][0]["label_name"] == "walking"


@pytest.mark.asyncio
async def test_get_application_not_found(client: AsyncClient) -> None:
    """GET /applications/{id} returns 404 when not found or not owned by user."""
    from app.exceptions import NotFoundError

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.applications_service.ApplicationsService.get_application",
        new_callable=AsyncMock,
        side_effect=NotFoundError(f"Application {FAKE_APP_ID}"),
    ):
        response = await client.get(
            f"/applications/{FAKE_APP_ID}", headers=AUTH_HEADERS
        )

    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404
