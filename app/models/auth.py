from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class OtpSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="Email address to send OTP to")


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="Email address that received the OTP")
    token: str = Field(..., description="6-digit OTP code")


class AppleSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_token: str = Field(..., description="Apple identity JWT token")


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., description="Supabase refresh token")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OtpSendResponse(BaseModel):
    message: str


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
