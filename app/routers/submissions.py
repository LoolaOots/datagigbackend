# app/routers/submissions.py
import structlog
from fastapi import APIRouter

from app.dependencies import CurrentUser, DBConn
from app.models.submissions import (
    ConfirmSubmissionRequest,
    ConfirmSubmissionResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services.submissions_service import SubmissionsService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])
_service = SubmissionsService()


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    body: UploadUrlRequest,
    current_user: CurrentUser,
    conn: DBConn,
) -> UploadUrlResponse:
    user_id = current_user["sub"]
    result = await _service.get_upload_url(
        conn,
        user_id=user_id,
        assignment_code=body.assignment_code,
        gig_label_id=body.gig_label_id,
        device_type=body.device_type,
        file_extension=body.file_extension,
    )
    return UploadUrlResponse(**result)


@router.post("/confirm", response_model=ConfirmSubmissionResponse)
async def confirm_submission(
    body: ConfirmSubmissionRequest,
    current_user: CurrentUser,
    conn: DBConn,
) -> ConfirmSubmissionResponse:
    user_id = current_user["sub"]
    result = await _service.confirm_submission(
        conn,
        user_id=user_id,
        application_id=body.application_id,
        gig_label_id=body.gig_label_id,
        assignment_code=body.assignment_code,
        storage_path=body.storage_path,
        file_size_bytes=body.file_size_bytes,
        duration_seconds=body.duration_seconds,
        device_metadata=body.device_metadata.model_dump(),
    )
    return ConfirmSubmissionResponse(**result)
