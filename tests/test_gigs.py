"""Tests for GET /gigs and GET /gigs/{gig_id}."""
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.exceptions import NotFoundError
from app.models.gigs import GigDetail, GigLabel, GigSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_override(mock_conn: Any):
    """Return an async generator dependency override that yields mock_conn."""

    async def _override() -> AsyncIterator[Any]:
        yield mock_conn

    return _override


def _make_gig_summary(**overrides: Any) -> GigSummary:
    defaults: dict[str, Any] = {
        "id": "gig-uuid-001",
        "title": "Horse Riding Sensor Data",
        "description": "Collect sensor data while riding a horse",
        "activity_type": "horse_riding",
        "status": "open",
        "total_slots": 20,
        "filled_slots": 4,
        "application_deadline": datetime(2026, 4, 1, tzinfo=timezone.utc),
        "data_deadline": datetime(2026, 4, 15, tzinfo=timezone.utc),
        "company_name": "Equine Research Co",
        "min_rate_cents": 500,
        "max_rate_cents": 1000,
        "device_types": ["generic_ios", "apple_watch"],
    }
    defaults.update(overrides)
    return GigSummary(**defaults)


def _make_gig_detail(**overrides: Any) -> GigDetail:
    label = GigLabel(
        id="label-uuid-001",
        label_name="walking on horse",
        description="Walk the horse at a steady pace",
        duration_seconds=120,
        rate_cents=500,
        quantity_needed=20,
        quantity_fulfilled=4,
    )
    defaults: dict[str, Any] = {
        "id": "gig-uuid-001",
        "title": "Horse Riding Sensor Data",
        "description": "Collect sensor data while riding a horse",
        "activity_type": "horse_riding",
        "status": "open",
        "total_slots": 20,
        "filled_slots": 4,
        "application_deadline": datetime(2026, 4, 1, tzinfo=timezone.utc),
        "data_deadline": datetime(2026, 4, 15, tzinfo=timezone.utc),
        "company_name": "Equine Research Co",
        "labels": [label],
        "device_types": ["generic_ios"],
    }
    defaults.update(overrides)
    return GigDetail(**defaults)


# ---------------------------------------------------------------------------
# GET /gigs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gigs_list_success(client: AsyncClient) -> None:
    """GET /gigs should return a list of open gig summaries."""
    mock_gigs = [_make_gig_summary(), _make_gig_summary(id="gig-uuid-002", title="Cycling Data")]
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.gigs_service.GigsService.list_gigs",
        return_value=mock_gigs,
    ):
        response = await client.get("/gigs")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["id"] == "gig-uuid-001"
    assert body[0]["company_name"] == "Equine Research Co"
    assert "device_types" in body[0]


@pytest.mark.asyncio
async def test_gigs_list_empty(client: AsyncClient) -> None:
    """GET /gigs should return an empty list when there are no open gigs."""
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.gigs_service.GigsService.list_gigs",
        return_value=[],
    ):
        response = await client.get("/gigs")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_gigs_list_pagination_params(client: AsyncClient) -> None:
    """GET /gigs passes page and limit to the service."""
    mock_conn = AsyncMock()
    captured: dict[str, Any] = {}

    async def fake_list_gigs(self: Any, conn: Any, page: int, limit: int) -> list[GigSummary]:
        captured["page"] = page
        captured["limit"] = limit
        return []

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.gigs_service.GigsService.list_gigs",
        new=fake_list_gigs,
    ):
        response = await client.get("/gigs?page=3&limit=10")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["page"] == 3
    assert captured["limit"] == 10


@pytest.mark.asyncio
async def test_gigs_list_limit_max_enforced(client: AsyncClient) -> None:
    """GET /gigs with limit > 50 should return 422."""
    response = await client.get("/gigs?limit=100")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_gigs_list_page_min_enforced(client: AsyncClient) -> None:
    """GET /gigs with page < 1 should return 422."""
    response = await client.get("/gigs?page=0")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /gigs/{gig_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gig_detail_success(client: AsyncClient) -> None:
    """GET /gigs/{id} should return full gig detail including labels."""
    mock_detail = _make_gig_detail()
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.gigs_service.GigsService.get_gig",
        return_value=mock_detail,
    ):
        response = await client.get("/gigs/gig-uuid-001")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "gig-uuid-001"
    assert body["title"] == "Horse Riding Sensor Data"
    assert isinstance(body["labels"], list)
    assert len(body["labels"]) == 1
    assert body["labels"][0]["label_name"] == "walking on horse"
    assert isinstance(body["device_types"], list)


@pytest.mark.asyncio
async def test_gig_detail_not_found(client: AsyncClient) -> None:
    """GET /gigs/{id} should return 404 when gig does not exist."""
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.gigs_service.GigsService.get_gig",
        side_effect=NotFoundError("Gig nonexistent-id"),
    ):
        response = await client.get("/gigs/nonexistent-id")

    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_gig_detail_response_shape(client: AsyncClient) -> None:
    """GET /gigs/{id} response should contain all required fields."""
    mock_detail = _make_gig_detail()
    mock_conn = AsyncMock()

    from app.main import app
    from app.dependencies import get_db

    app.dependency_overrides[get_db] = _make_db_override(mock_conn)

    with patch(
        "app.services.gigs_service.GigsService.get_gig",
        return_value=mock_detail,
    ):
        response = await client.get("/gigs/gig-uuid-001")

    app.dependency_overrides.clear()

    body = response.json()
    required_fields = {
        "id", "title", "description", "activity_type", "status",
        "total_slots", "filled_slots", "application_deadline",
        "data_deadline", "company_name", "labels", "device_types",
    }
    assert required_fields.issubset(body.keys())
