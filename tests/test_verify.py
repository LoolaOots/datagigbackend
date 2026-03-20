"""Tests for POST /verify."""
import io
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from httpx import AsyncClient

INTERNAL_SECRET = "test-internal-secret"
HEADERS = {"x-internal-secret": INTERNAL_SECRET}

VALID_PAYLOAD = {
    "submission_id": "sub-uuid-123",
    "storage_path": "submissions/user/app/label/1234567890.csv",
    "gig_label_id": "label-uuid-456",
    "duration_seconds": 10,
    "device_type": "generic_ios",
}


def _make_csv_bytes(rows: int = 500, hz: float = 50.0) -> bytes:
    """Generate a minimal sensor CSV with a timestamp column."""
    import numpy as np

    timestamps = (1_700_000_000_000 + (1000 / hz) * np.arange(rows)).astype(int)
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "ax": np.random.randn(rows),
            "ay": np.random.randn(rows),
            "az": np.random.randn(rows),
        }
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_verify_missing_auth_header(client: AsyncClient) -> None:
    """POST /verify without internal secret should return 422 (missing header)."""
    response = await client.post("/verify", json=VALID_PAYLOAD)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_verify_wrong_secret(client: AsyncClient) -> None:
    """POST /verify with wrong secret should return 401."""
    response = await client.post(
        "/verify",
        json=VALID_PAYLOAD,
        headers={"x-internal-secret": "wrong-secret"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_passing_submission(client: AsyncClient) -> None:
    """POST /verify with a valid CSV that matches duration should pass."""
    csv_bytes = _make_csv_bytes(rows=500, hz=50.0)  # 10 s at 50 Hz

    with patch(
        "app.services.verification_service.VerificationService._download",
        return_value=csv_bytes,
    ):
        response = await client.post("/verify", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert "passed" in body
    assert "result" in body
    assert isinstance(body["result"]["issues"], list)


@pytest.mark.asyncio
async def test_verify_empty_csv_fails(client: AsyncClient) -> None:
    """POST /verify with an empty CSV should return passed=False."""
    empty_csv = b"timestamp,ax,ay,az\n"

    with patch(
        "app.services.verification_service.VerificationService._download",
        return_value=empty_csv,
    ):
        response = await client.post("/verify", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert len(body["result"]["issues"]) > 0
