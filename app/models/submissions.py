# app/models/submissions.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class DeviceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    os_version: str


class UploadUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_code: str
    gig_label_id: str
    device_type: str
    file_extension: Literal["csv", "bin", "json"]


class UploadUrlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
    model_config = ConfigDict(from_attributes=True)
    submission_id: str
