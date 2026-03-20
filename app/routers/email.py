import structlog
from fastapi import APIRouter

from app.dependencies import InternalAuth
from app.models.email import EmailRequest, EmailResponse
from app.services.email_service import EmailService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/email", tags=["email"])

_service = EmailService()


@router.post("/send", response_model=EmailResponse)
async def send_email(
    body: EmailRequest,
    _auth: InternalAuth,
) -> EmailResponse:
    """
    Send a transactional email via Resend.

    Requires x-internal-secret header.
    """
    logger.info(
        "email_send_request_received",
        to=body.to,
        subject=body.subject,
    )

    return await _service.send(body)
