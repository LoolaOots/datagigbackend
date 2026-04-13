# app/services/submissions_service.py
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from asyncpg import Connection
from supabase import create_client  # type: ignore[import-untyped]

from app.config import settings

logger = structlog.get_logger(__name__)

_GET_APPLICATION_BY_CODE = """
    SELECT id, user_id, gig_id
    FROM applications
    WHERE assignment_code = $1
"""

_GET_GIG_LABEL = """
    SELECT id
    FROM gig_labels
    WHERE id = $1 AND gig_id = $2
"""

_INSERT_SUBMISSION = """
    INSERT INTO submissions (user_id, application_id, gig_label_id, storage_path, status, device_type, created_at, updated_at)
    VALUES ($1, $2, $3, $4, 'pending', $5, now(), now())
    RETURNING id
"""

_GET_SUBMISSION = """
    SELECT id, status
    FROM submissions
    WHERE application_id = $1 AND gig_label_id = $2 AND storage_path = $3 AND user_id = $4
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


class SubmissionsService:
    async def get_upload_url(
        self,
        conn: Connection,
        *,
        user_id: str,
        assignment_code: str,
        gig_label_id: str,
        device_type: str,
        file_extension: str,
    ) -> dict[str, Any] | None:
        """
        Returns dict with signed_url, storage_path, application_id
        or None if assignment_code not found / not owned / gig_label_id invalid.
        """
        log = logger.bind(user_id=user_id, assignment_code=assignment_code)

        application = await conn.fetchrow(_GET_APPLICATION_BY_CODE, assignment_code)
        if application is None or str(application["user_id"]) != user_id:
            log.info("application not found or not owned")
            return None

        gig_label = await conn.fetchrow(
            _GET_GIG_LABEL, gig_label_id, str(application["gig_id"])
        )
        if gig_label is None:
            log.info("gig_label not found in application gig")
            return None

        application_id = str(application["id"])
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        storage_path = f"submissions/{user_id}/{application_id}/{gig_label_id}/{timestamp}.{file_extension}"

        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)  # credentials
        signed = supabase.storage.from_("sensor-data").create_signed_upload_url(storage_path)
        # Supabase returns {"signedURL": "...", "token": "..."}
        # The signedURL already embeds the token — iOS only needs the URL
        signed_url = signed["signedURL"]

        submission_id = await conn.fetchval(
            _INSERT_SUBMISSION,
            user_id,
            application_id,
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
        storage_path: str,
        file_size_bytes: int,
        duration_seconds: int,
        device_metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Returns dict with submission_id, or None if not found/not owned.
        Idempotent: returns existing submission_id if already uploaded.
        """
        log = logger.bind(user_id=user_id, application_id=application_id)

        row = await conn.fetchrow(
            _GET_SUBMISSION, application_id, gig_label_id, storage_path, user_id
        )
        if row is None:
            log.info("submission not found")
            return None

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
