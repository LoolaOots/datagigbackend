# app/services/submissions_service.py
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

import structlog
from asyncpg import Connection
from supabase import create_client  # type: ignore[import-untyped]

from app.config import settings
from app.exceptions import NotFoundError

logger = structlog.get_logger(__name__)

_GET_APPLICATION_BY_CODE = """
    SELECT a.id, a.user_id, a.gig_id, g.title AS gig_title, cp.company_name
    FROM applications a
    JOIN gigs g ON g.id = a.gig_id
    JOIN company_profiles cp ON cp.user_id = g.company_id
    WHERE a.assignment_code = $1
"""

_GET_GIG_LABEL = """
    SELECT id, label_name
    FROM gig_labels
    WHERE id = $1 AND gig_id = $2
"""

_INSERT_SUBMISSION = """
    INSERT INTO submissions (user_id, application_id, gig_id, gig_label_id, storage_path, status, device_type, created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, 'pending', $6, now(), now())
    RETURNING id
"""

_GET_SUBMISSION = """
    SELECT s.id, s.status
    FROM submissions s
    JOIN applications a ON a.id = s.application_id
    WHERE s.application_id = $1
      AND s.gig_label_id = $2
      AND s.storage_path = $3
      AND s.user_id = $4
      AND a.assignment_code = $5
"""

_UPDATE_SUBMISSION_UPLOADED = """
    UPDATE submissions
    SET status = 'uploaded',
        file_size_bytes = $2,
        duration_seconds = $3,
        device_metadata = $4::jsonb,
        updated_at = now()
    WHERE id = $1
"""


def _sanitize_name(name: str) -> str:
    """Lowercase, replace non-alphanumeric runs with underscores, strip leading/trailing underscores."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class SubmissionsService:
    @staticmethod
    def _create_signed_upload_url(storage_path: str) -> str:
        """Synchronous helper — called via asyncio.to_thread."""
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)  # credentials
        signed = supabase.storage.from_("sensor-data").create_signed_upload_url(
            storage_path
        )
        return signed["signed_url"]

    async def get_upload_url(
        self,
        conn: Connection,
        *,
        user_id: str,
        assignment_code: str,
        gig_label_id: str,
        device_type: str,
        file_extension: str,
    ) -> dict[str, Any]:
        """
        Returns dict with signed_url, storage_path, application_id.
        Raises NotFoundError if assignment_code not found / not owned / gig_label_id invalid.
        """
        log = logger.bind(user_id=user_id, assignment_code=assignment_code)

        application = await conn.fetchrow(_GET_APPLICATION_BY_CODE, assignment_code)
        if application is None or str(application["user_id"]) != user_id:
            log.info("application not found or not owned")
            raise NotFoundError("Assignment or label")

        gig_label = await conn.fetchrow(
            _GET_GIG_LABEL, gig_label_id, str(application["gig_id"])
        )
        if gig_label is None:
            log.info("gig_label not found in application gig")
            raise NotFoundError("Assignment or label")

        application_id = str(application["id"])
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        company_sanitized = _sanitize_name(application["company_name"])
        gig_sanitized = _sanitize_name(application["gig_title"])
        label_sanitized = _sanitize_name(gig_label["label_name"])
        storage_path = f"submissions/{company_sanitized}/{gig_sanitized}/{label_sanitized}/{timestamp_ms}_{label_sanitized}.csv"

        signed_url = await asyncio.to_thread(self._create_signed_upload_url, storage_path)

        gig_id = str(application["gig_id"])
        submission_id = await conn.fetchval(
            _INSERT_SUBMISSION,
            user_id,
            application_id,
            gig_id,
            gig_label_id,
            storage_path,
            device_type,
        )

        log.info("submission pending created", submission_id=str(submission_id))
        return {
            "signed_url": signed_url,
            "storage_path": storage_path,
            "application_id": application_id,
        }

    async def confirm_submission(
        self,
        conn: Connection,
        *,
        user_id: str,
        application_id: str,
        gig_label_id: str,
        assignment_code: str,
        storage_path: str,
        file_size_bytes: int,
        duration_seconds: int,
        device_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Returns dict with submission_id.
        Idempotent: returns existing submission_id if already uploaded.
        Raises NotFoundError if submission not found / not owned.
        """
        log = logger.bind(user_id=user_id, application_id=application_id)

        row = await conn.fetchrow(
            _GET_SUBMISSION, application_id, gig_label_id, storage_path, user_id, assignment_code
        )
        if row is None:
            log.info("submission not found")
            raise NotFoundError("Submission")

        if row["status"] == "uploaded":
            log.info("submission already uploaded (idempotent)")
            return {"submission_id": str(row["id"])}

        # asyncpg requires json.dumps() for JSONB columns — raw dict is not accepted
        await conn.execute(
            _UPDATE_SUBMISSION_UPLOADED,
            row["id"],
            file_size_bytes,
            duration_seconds,
            json.dumps(device_metadata),
        )

        log.info("submission confirmed uploaded", submission_id=str(row["id"]))
        return {"submission_id": str(row["id"])}
