import structlog
from fastapi import APIRouter

from app.dependencies import CurrentUser, DBConn
from app.models.profile import ProfileResponse
from app.services.profile_service import ProfileService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

_service = ProfileService()


@router.get("", response_model=ProfileResponse)
async def get_profile(
    conn: DBConn,
    current_user: CurrentUser,
) -> ProfileResponse:
    """
    Get the authenticated user's profile (display name and credits balance).

    Requires Bearer token authentication.
    Returns 404 if no profile row exists for the user.
    """
    user_id: str = current_user["sub"]
    logger.info("get_profile_endpoint", user_id=user_id)
    return await _service.get_profile(conn, user_id=user_id)
