from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateApplicationRequest(BaseModel):
    """Body for POST /applications."""

    model_config = ConfigDict(extra="forbid")

    gig_id: str = Field(..., description="UUID of the gig to apply to")
    device_type: str = Field(..., description="Device type: generic_ios | apple_watch | generic_android")
    note_from_user: str | None = Field(None, max_length=500, description="Optional note from applicant")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ApplicationCreatedResponse(BaseModel):
    """Response body for POST /applications."""

    id: str
    gig_id: str
    status: str
    applied_at: datetime


class ApplicationLabelDetail(BaseModel):
    """A gig label nested inside GET /applications/{id}."""

    id: str
    label_name: str
    duration_seconds: int | None
    rate_cents: int


class ApplicationGigDetail(BaseModel):
    """Gig detail nested inside GET /applications/{id}."""

    title: str
    description: str | None
    activity_type: str | None
    data_deadline: datetime | None
    labels: list[ApplicationLabelDetail] = Field(default_factory=list)


class ApplicationListItem(BaseModel):
    """Single item returned by GET /applications."""

    id: str
    gig_id: str
    gig_title: str | None
    status: str
    device_type: str
    assignment_code: str | None
    applied_at: datetime
    note_from_company: str | None


class ApplicationDetailResponse(ApplicationListItem):
    """Full response for GET /applications/{id} — extends list item with extra fields."""

    note_from_user: str | None
    gig_detail: ApplicationGigDetail
