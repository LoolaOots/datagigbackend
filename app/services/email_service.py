import structlog
import resend  # type: ignore[import-untyped]

from app.config import settings
from app.exceptions import AppError
from app.models.email import EmailRequest, EmailResponse

logger = structlog.get_logger(__name__)


class EmailService:
    """Sends transactional emails via the Resend SDK."""

    async def send(self, request: EmailRequest) -> EmailResponse:
        resend.api_key = settings.resend_api_key

        params: resend.Emails.SendParams = {  # type: ignore[attr-defined]
            "from": request.from_address,
            "to": request.to,
            "subject": request.subject,
            "html": request.html,
        }

        try:
            result = resend.Emails.send(params)  # type: ignore[attr-defined]
            email_id: str = result.get("id", "") if isinstance(result, dict) else str(result.id)
            logger.info(
                "email_sent",
                email_id=email_id,
                to=request.to,
                subject=request.subject,
            )
            return EmailResponse(id=email_id, success=True)
        except Exception as exc:
            logger.error(
                "email_send_failed",
                to=request.to,
                subject=request.subject,
                error=str(exc),
            )
            raise AppError(f"Failed to send email: {exc}", status_code=502) from exc
