from pydantic import BaseModel, ConfigDict, Field


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(..., description="UUID of the submission")
    storage_path: str = Field(..., description="Supabase Storage path to the CSV file")
    gig_label_id: str = Field(..., description="UUID of the gig label")
    duration_seconds: int = Field(..., description="Expected duration in seconds")
    device_type: str = Field(..., description="Device type identifier, e.g. 'generic_ios'")


class VerificationResult(BaseModel):
    actual_duration_seconds: float = Field(..., description="Measured duration of the recording")
    sample_count: int = Field(..., description="Total number of data rows in the CSV")
    sample_rate_hz: float = Field(..., description="Inferred sample rate in Hz")
    issues: list[str] = Field(default_factory=list, description="List of validation issue messages")


class VerifyResponse(BaseModel):
    passed: bool = Field(..., description="Whether the submission passed verification")
    result: VerificationResult
