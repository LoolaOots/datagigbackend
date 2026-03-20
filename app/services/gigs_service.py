from typing import Any

import structlog
from asyncpg import Connection  # type: ignore[import-untyped]

from app.exceptions import NotFoundError
from app.models.gigs import GigDetail, GigLabel, GigSummary

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

_GIGS_LIST_SQL = """
SELECT
    g.id::text,
    g.title,
    g.description,
    g.activity_type,
    g.status,
    g.total_slots,
    g.filled_slots,
    g.application_deadline,
    g.data_deadline,
    cp.company_name,
    MIN(gl.rate_cents)::int AS min_rate_cents,
    MAX(gl.rate_cents)::int AS max_rate_cents,
    ARRAY_REMOVE(ARRAY_AGG(DISTINCT gdr.device_type), NULL) AS device_types
FROM gigs g
LEFT JOIN company_profiles cp ON cp.user_id = g.company_id
LEFT JOIN gig_labels gl ON gl.gig_id = g.id
LEFT JOIN gig_device_requirements gdr ON gdr.gig_id = g.id
WHERE g.status = 'open'
GROUP BY g.id, g.title, g.description, g.activity_type, g.status,
         g.total_slots, g.filled_slots, g.application_deadline,
         g.data_deadline, cp.company_name
ORDER BY g.created_at DESC
LIMIT $1 OFFSET $2
"""

_GIG_DETAIL_SQL = """
SELECT
    g.id::text,
    g.title,
    g.description,
    g.activity_type,
    g.status,
    g.total_slots,
    g.filled_slots,
    g.application_deadline,
    g.data_deadline,
    cp.company_name,
    ARRAY_REMOVE(ARRAY_AGG(DISTINCT gdr.device_type), NULL) AS device_types
FROM gigs g
LEFT JOIN company_profiles cp ON cp.user_id = g.company_id
LEFT JOIN gig_device_requirements gdr ON gdr.gig_id = g.id
WHERE g.id = $1
GROUP BY g.id, g.title, g.description, g.activity_type, g.status,
         g.total_slots, g.filled_slots, g.application_deadline,
         g.data_deadline, cp.company_name
"""

_GIG_LABELS_SQL = """
SELECT
    id::text,
    label_name,
    description,
    duration_seconds,
    rate_cents,
    quantity_needed,
    quantity_fulfilled
FROM gig_labels
WHERE gig_id = $1
ORDER BY created_at ASC
"""


def _record_to_summary(row: Any) -> GigSummary:
    device_types: list[str] = list(row["device_types"]) if row["device_types"] else []
    return GigSummary(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        activity_type=row["activity_type"],
        status=row["status"],
        total_slots=row["total_slots"],
        filled_slots=row["filled_slots"],
        application_deadline=row["application_deadline"],
        data_deadline=row["data_deadline"],
        company_name=row["company_name"],
        min_rate_cents=row["min_rate_cents"],
        max_rate_cents=row["max_rate_cents"],
        device_types=device_types,
    )


def _record_to_label(row: Any) -> GigLabel:
    return GigLabel(
        id=row["id"],
        label_name=row["label_name"],
        description=row["description"],
        duration_seconds=row["duration_seconds"],
        rate_cents=row["rate_cents"],
        quantity_needed=row["quantity_needed"],
        quantity_fulfilled=row["quantity_fulfilled"],
    )


class GigsService:
    """All asyncpg queries for the gigs endpoints."""

    async def list_gigs(
        self, conn: Connection, page: int, limit: int
    ) -> list[GigSummary]:
        offset = (page - 1) * limit
        logger.info("gigs_list_query", page=page, limit=limit, offset=offset)
        rows = await conn.fetch(_GIGS_LIST_SQL, limit, offset)
        return [_record_to_summary(r) for r in rows]

    async def get_gig(self, conn: Connection, gig_id: str) -> GigDetail:
        logger.info("gig_detail_query", gig_id=gig_id)

        row = await conn.fetchrow(_GIG_DETAIL_SQL, gig_id)
        if row is None:
            raise NotFoundError(f"Gig {gig_id}")

        label_rows = await conn.fetch(_GIG_LABELS_SQL, gig_id)
        labels = [_record_to_label(r) for r in label_rows]
        device_types: list[str] = list(row["device_types"]) if row["device_types"] else []

        return GigDetail(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            activity_type=row["activity_type"],
            status=row["status"],
            total_slots=row["total_slots"],
            filled_slots=row["filled_slots"],
            application_deadline=row["application_deadline"],
            data_deadline=row["data_deadline"],
            company_name=row["company_name"],
            labels=labels,
            device_types=device_types,
        )
