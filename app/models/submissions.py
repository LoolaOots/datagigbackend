# app/models/submissions.py
from pydantic import BaseModel, ConfigDict


class DeviceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    os_version: str


class UploadUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_code: str
    gig_label_id: str
    device_type: str
    file_extension: str


class UploadUrlResponse(BaseModel):
    signed_url: str
    storage_path: str
    application_id: str


class ConfirmSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: str
    gig_label_id: str
    assignment_code: str
    storage_path: str
    file_size_bytes: int
    duration_seconds: int
    device_type: str
    device_metadata: DeviceMetadata


class ConfirmSubmissionResponse(BaseModel):
    submission_id: str
