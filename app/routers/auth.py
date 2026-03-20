import structlog
from fastapi import APIRouter

from app.dependencies import DBConn
from app.models.auth import (
    AppleSignInRequest,
    AuthTokenResponse,
    OtpSendRequest,
    OtpSendResponse,
    OtpVerifyRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.auth_service import AuthService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_service = AuthService()


@router.post("/otp/send", response_model=OtpSendResponse)
async def send_otp(body: OtpSendRequest) -> OtpSendResponse:
    """
    Send a 6-digit OTP to the user's email via Supabase Auth.
    No authentication required.
    """
    logger.info("otp_send_endpoint", email=body.email)
    await _service.send_otp(str(body.email))
    return OtpSendResponse(message="OTP sent")


@router.post("/otp/verify", response_model=AuthTokenResponse)
async def verify_otp(body: OtpVerifyRequest, conn: DBConn) -> AuthTokenResponse:
    """
    Verify a 6-digit OTP, return access + refresh tokens.
    Creates users/user_profiles rows on first sign-in.
    No authentication required.
    """
    logger.info("otp_verify_endpoint", email=body.email)
    result = await _service.verify_otp(str(body.email), body.token, conn)
    return AuthTokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        user_id=result["user_id"],
    )


@router.post("/apple", response_model=AuthTokenResponse)
async def apple_sign_in(body: AppleSignInRequest, conn: DBConn) -> AuthTokenResponse:
    """
    Exchange an Apple identity JWT for a Supabase session.
    Creates users/user_profiles rows on first sign-in.
    No authentication required.
    """
    logger.info("apple_signin_endpoint")
    result = await _service.sign_in_apple(body.identity_token, conn)
    return AuthTokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        user_id=result["user_id"],
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(body: RefreshTokenRequest) -> RefreshTokenResponse:
    """
    Refresh an expired access token using a refresh token.
    No authentication required.
    """
    logger.info("token_refresh_endpoint")
    result = await _service.refresh_session(body.refresh_token)
    return RefreshTokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )
