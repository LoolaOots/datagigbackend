import structlog
from fastapi import APIRouter, Query

from app.dependencies import DBConn
from app.models.gigs import GigDetail, GigSummary
from app.services.gigs_service import GigsService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/gigs", tags=["gigs"])

_service = GigsService()


@router.get("", response_model=list[GigSummary])
async def list_gigs(
    conn: DBConn,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=20, ge=1, le=50, description="Results per page (max 50)"),
) -> list[GigSummary]:
    """
    List open gigs with aggregated label rates and device requirements.
    No authentication required.
    """
    logger.info("gigs_list_endpoint", page=page, limit=limit)
    return await _service.list_gigs(conn, page=page, limit=limit)


@router.get("/{gig_id}", response_model=GigDetail)
async def get_gig(gig_id: str, conn: DBConn) -> GigDetail:
    """
    Get full detail for a single gig including labels and device requirements.
    Returns 404 if the gig does not exist.
    No authentication required.
    """
    logger.info("gig_detail_endpoint", gig_id=gig_id)
    return await _service.get_gig(conn, gig_id=gig_id)
