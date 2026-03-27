from typing import Any

import structlog
from asyncpg import Connection  # type: ignore[import-untyped]

from app.exceptions import AppError, NotFoundError
from app.models.applications import (
    ApplicationCreatedResponse,
    ApplicationDetailResponse,
    ApplicationGigDetail,
    ApplicationLabelDetail,
    ApplicationListItem,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_VALID_DEVICE_TYPES = {"generic_ios", "apple_watch", "generic_android"}

_CHECK_GIG_SQL = """
SELECT id::text, status, filled_slots, total_slots
FROM gigs
WHERE id = $1
"""

_CHECK_DEVICE_REQUIREMENT_SQL = """
SELECT 1
FROM gig_device_requirements
WHERE gig_id = $1
  AND device_type = $2::device_type
"""

_CHECK_EXISTING_APPLICATION_SQL = """
SELECT 1
FROM applications
WHERE gig_id = $1
  AND user_id = $2
"""

_INSERT_APPLICATION_SQL = """
INSERT INTO applications (gig_id, user_id, device_type, note_from_user)
VALUES ($1, $2, $3, $4)
RETURNING id::text, gig_id::text, status, applied_at
"""

_LIST_APPLICATIONS_SQL = """
SELECT
    a.id::text,
    a.gig_id::text,
    g.title AS gig_title,
    a.status,
    a.device_type,
    a.assignment_code,
    a.applied_at,
    a.note_from_company
FROM applications a
LEFT JOIN gigs g ON g.id = a.gig_id
WHERE a.user_id = $1
ORDER BY a.applied_at DESC
"""

_GET_APPLICATION_SQL = """
SELECT
    a.id::text,
    a.gig_id::text,
    g.title AS gig_title,
    a.status,
    a.device_type,
    a.assignment_code,
    a.applied_at,
    a.note_from_company,
    a.note_from_user,
    g.description AS gig_description,
    g.activity_type AS gig_activity_type,
    g.data_deadline AS gig_data_deadline,
    cp.company_name
FROM applications a
LEFT JOIN gigs g ON g.id = a.gig_id
LEFT JOIN company_profiles cp ON cp.user_id = g.company_id
WHERE a.id = $1
  AND a.user_id = $2
"""

_GET_GIG_LABELS_SQL = """
SELECT
    id::text,
    label_name,
    description,
    duration_seconds,
    rate_cents
FROM gig_labels
WHERE gig_id = $1
ORDER BY created_at ASC
"""


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class ApplicationsService:
    """All asyncpg queries for the applications endpoints."""

    async def create_application(
        self,
        conn: Connection,
        user_id: str,
        gig_id: str,
        device_type: str,
        note_from_user: str | None,
    ) -> ApplicationCreatedResponse:
        # Validate device_type value
        if device_type not in _VALID_DEVICE_TYPES:
            raise AppError(
                f"Invalid device_type '{device_type}'. Must be one of: {', '.join(sorted(_VALID_DEVICE_TYPES))}",
                status_code=422,
            )

        # Check gig exists, is open, and has available slots
        gig_row: Any = await conn.fetchrow(_CHECK_GIG_SQL, gig_id)
        if gig_row is None:
            raise NotFoundError(f"Gig {gig_id}")
        if gig_row["status"] != "open":
            raise AppError("Gig is not open for applications", status_code=400)
        if gig_row["filled_slots"] >= gig_row["total_slots"]:
            raise AppError("Gig has no available slots", status_code=400)

        # Check device type is in the gig's requirements
        device_allowed: Any = await conn.fetchrow(
            _CHECK_DEVICE_REQUIREMENT_SQL, gig_id, device_type
        )
        if device_allowed is None:
            raise AppError(
                f"Device type '{device_type}' is not accepted for this gig",
                status_code=400,
            )

        # Check user has not already applied
        existing: Any = await conn.fetchrow(
            _CHECK_EXISTING_APPLICATION_SQL, gig_id, user_id
        )
        if existing is not None:
            raise AppError("You have already applied to this gig", status_code=409)

        # Insert application
        logger.info(
            "application_create",
            user_id=user_id,
            gig_id=gig_id,
            device_type=device_type,
        )
        row: Any = await conn.fetchrow(
            _INSERT_APPLICATION_SQL,
            gig_id,
            user_id,
            device_type,
            note_from_user,
        )

        return ApplicationCreatedResponse(
            id=row["id"],
            gig_id=row["gig_id"],
            status=row["status"],
            applied_at=row["applied_at"],
        )

    async def list_applications(
        self, conn: Connection, user_id: str
    ) -> list[ApplicationListItem]:
        logger.info("applications_list_query", user_id=user_id)
        rows = await conn.fetch(_LIST_APPLICATIONS_SQL, user_id)
        return [
            ApplicationListItem(
                id=r["id"],
                gig_id=r["gig_id"],
                gig_title=r["gig_title"],
                status=r["status"],
                device_type=r["device_type"],
                assignment_code=r["assignment_code"],
                applied_at=r["applied_at"],
                note_from_company=r["note_from_company"],
            )
            for r in rows
        ]

    async def get_application(
        self, conn: Connection, application_id: str, user_id: str
    ) -> ApplicationDetailResponse:
        logger.info(
            "application_detail_query",
            application_id=application_id,
            user_id=user_id,
        )
        row: Any = await conn.fetchrow(_GET_APPLICATION_SQL, application_id, user_id)
        if row is None:
            raise NotFoundError(f"Application {application_id}")

        gig_id = row["gig_id"]
        label_rows = await conn.fetch(_GET_GIG_LABELS_SQL, gig_id)
        labels = [
            ApplicationLabelDetail(
                id=lr["id"],
                label_name=lr["label_name"],
                description=lr["description"],
                duration_seconds=lr["duration_seconds"],
                rate_cents=lr["rate_cents"],
            )
            for lr in label_rows
        ]

        gig_detail = ApplicationGigDetail(
            title=row["gig_title"] or "",
            company_name=row["company_name"] or "",
            description=row["gig_description"],
            activity_type=row["gig_activity_type"],
            data_deadline=row["gig_data_deadline"],
            labels=labels,
        )

        return ApplicationDetailResponse(
            id=row["id"],
            gig_id=gig_id,
            gig_title=row["gig_title"],
            status=row["status"],
            device_type=row["device_type"],
            assignment_code=row["assignment_code"],
            applied_at=row["applied_at"],
            note_from_company=row["note_from_company"],
            note_from_user=row["note_from_user"],
            gig_detail=gig_detail,
        )
