from pydantic import BaseModel


class ProfileResponse(BaseModel):
    """Response body for GET /profile."""

    display_name: str | None
    credits_balance_cents: int
