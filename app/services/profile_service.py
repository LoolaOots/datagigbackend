from typing import Any

import structlog
from asyncpg import Connection  # type: ignore[import-untyped]

from app.exceptions import NotFoundError
from app.models.profile import ProfileResponse

logger = structlog.get_logger(__name__)

_GET_PROFILE_SQL = """
SELECT
    display_name,
    credits_balance_cents
FROM user_profiles
WHERE user_id = $1
"""


class ProfileService:
    """Asyncpg queries for the profile endpoint."""

    async def get_profile(self, conn: Connection, user_id: str) -> ProfileResponse:
        logger.info("profile_query", user_id=user_id)
        row: Any = await conn.fetchrow(_GET_PROFILE_SQL, user_id)
        if row is None:
            raise NotFoundError(f"Profile for user {user_id}")

        return ProfileResponse(
            display_name=row["display_name"],
            credits_balance_cents=row["credits_balance_cents"],
        )
