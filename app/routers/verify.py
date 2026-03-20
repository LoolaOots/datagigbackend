import structlog
from fastapi import APIRouter

from app.dependencies import InternalAuth
from app.models.verification import VerifyRequest, VerifyResponse
from app.services.verification_service import VerificationService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["verify"])

_service = VerificationService()


@router.post("/verify", response_model=VerifyResponse)
async def verify_submission(
    body: VerifyRequest,
    _auth: InternalAuth,
) -> VerifyResponse:
    """
    Verify a data submission.

    Called by the website's Inngest `submission/verify` job.
    Requires x-internal-secret header.
    """
    logger.info(
        "verify_request_received",
        submission_id=body.submission_id,
        storage_path=body.storage_path,
        duration_seconds=body.duration_seconds,
        device_type=body.device_type,
    )

    response = await _service.verify(
        storage_path=body.storage_path,
        duration_seconds=body.duration_seconds,
        device_type=body.device_type,
    )

    logger.info(
        "verify_request_completed",
        submission_id=body.submission_id,
        passed=response.passed,
    )

    return response
