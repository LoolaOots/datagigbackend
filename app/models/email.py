from pydantic import BaseModel, ConfigDict, Field


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: list[str] = Field(..., description="List of recipient email addresses")
    subject: str = Field(..., description="Email subject line")
    html: str = Field(..., description="HTML body of the email")
    from_address: str = Field(
        default="DataGigs <noreply@datagigs.com>",
        description="Sender address (defaults to DataGigs noreply)",
    )


class EmailResponse(BaseModel):
    id: str = Field(..., description="Resend message ID")
    success: bool = Field(..., description="Whether the email was accepted by Resend")
