import asyncio
import io

import pandas as pd
import structlog
from supabase import create_client  # type: ignore[import-untyped]

from app.config import settings
from app.exceptions import AppError
from app.models.verification import VerificationResult, VerifyResponse

logger = structlog.get_logger(__name__)

STORAGE_BUCKET = "sensor-data"
DURATION_TOLERANCE = 0.10  # 10 %
MAX_NAN_FRACTION = 0.05  # 5 %


def _parse_and_evaluate(
    csv_bytes: bytes,
    duration_seconds: int,
    device_type: str,
) -> VerifyResponse:
    """
    Pure CPU-bound function: parse CSV bytes and evaluate quality.
    Run via asyncio.to_thread() from the async entry point.
    """
    issues: list[str] = []

    try:
        df = pd.read_csv(io.BytesIO(csv_bytes))
    except Exception as exc:
        raise AppError(f"Failed to parse CSV: {exc}", status_code=422) from exc

    sample_count = len(df)

    if sample_count == 0:
        issues.append("CSV contains no data rows")
        return VerifyResponse(
            passed=False,
            result=VerificationResult(
                actual_duration_seconds=0.0,
                sample_count=0,
                sample_rate_hz=0.0,
                issues=issues,
            ),
        )

    # NaN check
    nan_fraction = df.isnull().any(axis=1).mean()
    if nan_fraction > MAX_NAN_FRACTION:
        issues.append(
            f"Too many rows with missing values: {nan_fraction:.1%} (limit {MAX_NAN_FRACTION:.0%})"
        )

    # Infer duration and sample rate from a timestamp column (if present)
    timestamp_col: str | None = None
    for candidate in ("timestamp", "time", "t", "Timestamp", "Time"):
        if candidate in df.columns:
            timestamp_col = candidate
            break

    if timestamp_col is not None:
        try:
            times = pd.to_numeric(df[timestamp_col], errors="coerce").dropna()
            if len(times) >= 2:
                t_min = float(times.min())
                t_max = float(times.max())
                # Detect if timestamps are in milliseconds (> 1e9 suggests ms since epoch)
                if t_max > 1e9:
                    actual_duration = (t_max - t_min) / 1000.0
                else:
                    actual_duration = t_max - t_min
                sample_rate = float(len(times)) / actual_duration if actual_duration > 0 else 0.0
            else:
                actual_duration = float(duration_seconds)
                sample_rate = float(sample_count) / actual_duration if actual_duration > 0 else 0.0
        except Exception:
            actual_duration = float(duration_seconds)
            sample_rate = float(sample_count) / actual_duration if actual_duration > 0 else 0.0
    else:
        # No timestamp column — estimate from row count assuming 50 Hz default
        default_hz = 50.0
        actual_duration = float(sample_count) / default_hz
        sample_rate = default_hz

    # Duration check
    lower = duration_seconds * (1 - DURATION_TOLERANCE)
    upper = duration_seconds * (1 + DURATION_TOLERANCE)
    if not (lower <= actual_duration <= upper):
        issues.append(
            f"Actual duration {actual_duration:.1f}s is outside expected range "
            f"[{lower:.1f}s, {upper:.1f}s] for {duration_seconds}s recording"
        )

    passed = len(issues) == 0

    logger.info(
        "verification_evaluated",
        device_type=device_type,
        sample_count=sample_count,
        actual_duration=actual_duration,
        sample_rate=sample_rate,
        passed=passed,
        issues=issues,
    )

    return VerifyResponse(
        passed=passed,
        result=VerificationResult(
            actual_duration_seconds=round(actual_duration, 3),
            sample_count=sample_count,
            sample_rate_hz=round(sample_rate, 3),
            issues=issues,
        ),
    )


class VerificationService:
    """Downloads sensor CSV from Supabase Storage and evaluates its quality."""

    async def verify(
        self,
        storage_path: str,
        duration_seconds: int,
        device_type: str,
    ) -> VerifyResponse:
        logger.info(
            "verification_started",
            storage_path=storage_path,
            duration_seconds=duration_seconds,
            device_type=device_type,
        )

        # Download from Supabase Storage using service role key
        try:
            csv_bytes = await asyncio.to_thread(self._download, storage_path)
        except Exception as exc:
            logger.error(
                "storage_download_failed",
                storage_path=storage_path,
                error=str(exc),
            )
            raise AppError(
                f"Failed to download file from storage: {exc}", status_code=502
            ) from exc

        # Offload pandas work to a thread so the event loop stays free
        return await asyncio.to_thread(
            _parse_and_evaluate, csv_bytes, duration_seconds, device_type
        )

    @staticmethod
    def _download(storage_path: str) -> bytes:
        """Synchronous helper — called via asyncio.to_thread."""
        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        result: bytes = client.storage.from_(STORAGE_BUCKET).download(storage_path)
        return result
