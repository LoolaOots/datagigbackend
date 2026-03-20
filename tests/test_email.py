"""Tests for POST /email/send."""
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

INTERNAL_SECRET = "test-internal-secret"
HEADERS = {"x-internal-secret": INTERNAL_SECRET}

VALID_PAYLOAD = {
    "to": ["recipient@example.com"],
    "subject": "Test Subject",
    "html": "<p>Hello, world!</p>",
}


@pytest.mark.asyncio
async def test_email_missing_auth_header(client: AsyncClient) -> None:
    """POST /email/send without internal secret should return 422 (missing header)."""
    response = await client.post("/email/send", json=VALID_PAYLOAD)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_email_wrong_secret(client: AsyncClient) -> None:
    """POST /email/send with wrong secret should return 401."""
    response = await client.post(
        "/email/send",
        json=VALID_PAYLOAD,
        headers={"x-internal-secret": "bad-secret"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_email_send_success(client: AsyncClient) -> None:
    """POST /email/send should call Resend and return success."""
    mock_result = MagicMock()
    mock_result.id = "resend-msg-id-001"

    with patch("resend.Emails.send", return_value={"id": "resend-msg-id-001"}):
        response = await client.post("/email/send", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["id"] == "resend-msg-id-001"


@pytest.mark.asyncio
async def test_email_send_with_custom_from(client: AsyncClient) -> None:
    """POST /email/send accepts a custom from_address."""
    payload = {**VALID_PAYLOAD, "from_address": "Custom <custom@example.com>"}

    with patch("resend.Emails.send", return_value={"id": "resend-msg-id-002"}):
        response = await client.post("/email/send", json=payload, headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_email_send_resend_failure(client: AsyncClient) -> None:
    """POST /email/send should return 502 if Resend raises an exception."""
    with patch("resend.Emails.send", side_effect=Exception("Resend API error")):
        response = await client.post("/email/send", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 502
