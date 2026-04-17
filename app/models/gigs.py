from datetime import datetime

from pydantic import BaseModel, Field


class GigSummary(BaseModel):
    """Gig list item returned by GET /gigs."""

    id: str
    title: str
    description: str | None
    activity_type: str | None
    status: str
    total_slots: int
    filled_slots: int
    application_deadline: datetime | None
    data_deadline: datetime | None
    company_name: str | None
    min_rate_cents: int | None = Field(None, description="Minimum rate in cents across all labels")
    max_rate_cents: int | None = Field(None, description="Maximum rate in cents across all labels")
    device_types: list[str] = Field(default_factory=list)


class GigLabel(BaseModel):
    """A single label (activity segment) belonging to a gig."""

    id: str
    label_name: str
    description: str | None
    duration_seconds: int | None
    rate_cents: int
    quantity_needed: int
    quantity_fulfilled: int


class GigDetail(BaseModel):
    """Full gig detail returned by GET /gigs/{gig_id}."""

    id: str
    title: str
    description: str | None
    activity_type: str | None
    status: str
    total_slots: int
    filled_slots: int
    application_deadline: datetime | None
    data_deadline: datetime | None
    company_name: str | None
    min_rate_cents: int | None = Field(None, description="Minimum rate in cents across all labels")
    max_rate_cents: int | None = Field(None, description="Maximum rate in cents across all labels")
    labels: list[GigLabel] = Field(default_factory=list)
    device_types: list[str] = Field(default_factory=list)
