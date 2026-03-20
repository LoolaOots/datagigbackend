import structlog
from fastapi import APIRouter

from app.dependencies import CurrentUser, DBConn
from app.models.applications import (
    ApplicationCreatedResponse,
    ApplicationDetailResponse,
    ApplicationListItem,
    CreateApplicationRequest,
)
from app.services.applications_service import ApplicationsService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/applications", tags=["applications"])

_service = ApplicationsService()


@router.post("", response_model=ApplicationCreatedResponse, status_code=201)
async def create_application(
    body: CreateApplicationRequest,
    conn: DBConn,
    current_user: CurrentUser,
) -> ApplicationCreatedResponse:
    """
    Apply to a gig.

    Requires Bearer token authentication.
    Validates gig is open, device type is accepted, and user has not already applied.
    """
    user_id: str = current_user["sub"]
    logger.info("create_application_endpoint", user_id=user_id, gig_id=body.gig_id)
    return await _service.create_application(
        conn,
        user_id=user_id,
        gig_id=body.gig_id,
        device_type=body.device_type,
        note_from_user=body.note_from_user,
    )


@router.get("", response_model=list[ApplicationListItem])
async def list_applications(
    conn: DBConn,
    current_user: CurrentUser,
) -> list[ApplicationListItem]:
    """
    List all applications for the authenticated user, ordered by applied_at DESC.

    Requires Bearer token authentication.
    """
    user_id: str = current_user["sub"]
    logger.info("list_applications_endpoint", user_id=user_id)
    return await _service.list_applications(conn, user_id=user_id)


@router.get("/{application_id}", response_model=ApplicationDetailResponse)
async def get_application(
    application_id: str,
    conn: DBConn,
    current_user: CurrentUser,
) -> ApplicationDetailResponse:
    """
    Get full detail for a single application including gig labels.

    Requires Bearer token authentication.
    Returns 404 if the application does not exist or does not belong to the current user.
    """
    user_id: str = current_user["sub"]
    logger.info(
        "get_application_endpoint",
        user_id=user_id,
        application_id=application_id,
    )
    return await _service.get_application(conn, application_id=application_id, user_id=user_id)
