# tests/test_submissions.py
import pytest
from unittest.mock import AsyncMock, patch

from app.dependencies import get_current_user
from app.exceptions import NotFoundError
from app.main import app

pytestmark = pytest.mark.asyncio


async def test_get_upload_url_success(client):
    def override_current_user():
        return {"sub": "user-123"}

    app.dependency_overrides[get_current_user] = override_current_user

    mock_result = {
        "signed_url": "https://storage.example.com/signed",
        "storage_path": "submissions/user-123/app-id/label-id/20260101T000000.csv",
        "application_id": "app-id",
    }

    with patch(
        "app.services.submissions_service.SubmissionsService.get_upload_url",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/submissions/upload-url",
            json={
                "assignment_code": "ABC123",
                "gig_label_id": "label-id",
                "device_type": "generic_ios",
                "file_extension": "csv",
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    data = response.json()
    # FastAPI serializes snake_case — iOS convertFromSnakeCase handles the rest
    assert data["signed_url"] == mock_result["signed_url"]
    assert data["storage_path"] == mock_result["storage_path"]
    assert data["application_id"] == mock_result["application_id"]

    app.dependency_overrides.clear()


async def test_get_upload_url_not_found(client):
    def override_current_user():
        return {"sub": "user-123"}

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.submissions_service.SubmissionsService.get_upload_url",
        new_callable=AsyncMock,
        side_effect=NotFoundError("Assignment or label"),
    ):
        response = await client.post(
            "/submissions/upload-url",
            json={
                "assignment_code": "BADCODE",
                "gig_label_id": "label-id",
                "device_type": "generic_ios",
                "file_extension": "csv",
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 404
    app.dependency_overrides.clear()


async def test_confirm_submission_success(client):
    def override_current_user():
        return {"sub": "user-123"}

    app.dependency_overrides[get_current_user] = override_current_user

    mock_result = {"submission_id": "sub-id-123"}

    with patch(
        "app.services.submissions_service.SubmissionsService.confirm_submission",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/submissions/confirm",
            json={
                "application_id": "app-id",
                "gig_label_id": "label-id",
                "assignment_code": "ABC123",
                "storage_path": "submissions/user-123/app-id/label-id/ts.csv",
                "file_size_bytes": 12345,
                "duration_seconds": 120,
                "device_type": "generic_ios",
                "device_metadata": {"model": "iPhone 16", "os_version": "26.0"},
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.json()["submission_id"] == "sub-id-123"
    app.dependency_overrides.clear()


async def test_confirm_submission_not_found(client):
    def override_current_user():
        return {"sub": "user-123"}

    app.dependency_overrides[get_current_user] = override_current_user

    with patch(
        "app.services.submissions_service.SubmissionsService.confirm_submission",
        new_callable=AsyncMock,
        side_effect=NotFoundError("Submission"),
    ):
        response = await client.post(
            "/submissions/confirm",
            json={
                "application_id": "app-id",
                "gig_label_id": "label-id",
                "assignment_code": "ABC123",
                "storage_path": "submissions/x/y/z/ts.csv",
                "file_size_bytes": 0,
                "duration_seconds": 0,
                "device_type": "generic_ios",
                "device_metadata": {"model": "iPhone 16", "os_version": "26.0"},
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 404
    app.dependency_overrides.clear()


async def test_confirm_submission_idempotent(client):
    """Already-uploaded submission returns 200 with same submission_id."""
    def override_current_user():
        return {"sub": "user-123"}

    app.dependency_overrides[get_current_user] = override_current_user

    mock_result = {"submission_id": "sub-id-already"}

    with patch(
        "app.services.submissions_service.SubmissionsService.confirm_submission",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/submissions/confirm",
            json={
                "application_id": "app-id",
                "gig_label_id": "label-id",
                "assignment_code": "ABC123",
                "storage_path": "submissions/user-123/app-id/label-id/ts.csv",
                "file_size_bytes": 12345,
                "duration_seconds": 120,
                "device_type": "generic_ios",
                "device_metadata": {"model": "iPhone 16", "os_version": "26.0"},
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.json()["submission_id"] == "sub-id-already"
    app.dependency_overrides.clear()
