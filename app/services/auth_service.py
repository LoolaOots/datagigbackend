import asyncio
from typing import Any

import structlog
from asyncpg import Connection  # type: ignore[import-untyped]
from supabase import Client, create_client  # type: ignore[import-untyped]

from app.config import settings
from app.exceptions import AuthError

logger = structlog.get_logger(__name__)


def _get_supabase_client() -> Client:
    """Return a supabase-py client using the service role key."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def _ensure_user_exists(conn: Connection, user_id: str, email: str) -> None:
    """
    Check if a users row exists; if not, insert users + user_profiles rows.
    This is called after a successful Supabase auth operation.
    """
    existing = await conn.fetchrow(
        "SELECT id FROM users WHERE id = $1",
        user_id,
    )
    if existing is not None:
        logger.info("user_already_exists", user_id=user_id)
        return

    logger.info("creating_new_user", user_id=user_id, email=email)

    # Insert into users
    await conn.execute(
        "INSERT INTO users (id, email, role) VALUES ($1, $2, $3)",
        user_id,
        email,
        "user",
    )

    # Insert into user_profiles — display_name is the email prefix before @
    display_name = email.split("@")[0]
    await conn.execute(
        "INSERT INTO user_profiles (user_id, display_name) VALUES ($1, $2)",
        user_id,
        display_name,
    )

    logger.info("user_created", user_id=user_id, display_name=display_name)


def _send_otp_sync(email: str) -> None:
    """Synchronous supabase-py call — run via asyncio.to_thread."""
    client = _get_supabase_client()
    client.auth.sign_in_with_otp({"email": email})


def _verify_otp_sync(email: str, token: str) -> dict[str, Any]:
    """Synchronous supabase-py call — run via asyncio.to_thread."""
    client = _get_supabase_client()
    response = client.auth.verify_otp({"email": email, "token": token, "type": "email"})
    if response.session is None or response.user is None:
        raise AuthError("OTP verification failed: no session returned")
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "user_id": str(response.user.id),
        "email": response.user.email or email,
    }


def _sign_in_apple_sync(identity_token: str) -> dict[str, Any]:
    """Synchronous supabase-py call — run via asyncio.to_thread."""
    client = _get_supabase_client()
    response = client.auth.sign_in_with_id_token(
        {"provider": "apple", "token": identity_token}
    )
    if response.session is None or response.user is None:
        raise AuthError("Apple sign-in failed: no session returned")
    email: str = response.user.email or ""
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "user_id": str(response.user.id),
        "email": email,
    }


def _refresh_session_sync(refresh_token: str) -> dict[str, Any]:
    """Synchronous supabase-py call — run via asyncio.to_thread."""
    client = _get_supabase_client()
    response = client.auth.refresh_session(refresh_token)
    if response.session is None:
        raise AuthError("Token refresh failed: no session returned")
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
    }


class AuthService:
    """Handles all auth operations: Supabase calls + user/profile row creation."""

    async def send_otp(self, email: str) -> None:
        """Trigger Supabase to email a 6-digit OTP to the user."""
        logger.info("otp_send_requested", email=email)
        try:
            await asyncio.to_thread(_send_otp_sync, email)
        except AuthError:
            raise
        except Exception as exc:
            logger.error("otp_send_failed", email=email, error=str(exc))
            raise AuthError("Failed to send OTP") from exc
        logger.info("otp_sent", email=email)

    async def verify_otp(
        self, email: str, token: str, conn: Connection
    ) -> dict[str, Any]:
        """Verify an OTP code, create user/profile rows if first sign-in."""
        logger.info("otp_verify_requested", email=email)
        try:
            result = await asyncio.to_thread(_verify_otp_sync, email, token)
        except AuthError:
            raise
        except Exception as exc:
            logger.error("otp_verify_failed", email=email, error=str(exc))
            raise AuthError("OTP verification failed") from exc

        await _ensure_user_exists(conn, result["user_id"], result["email"])
        logger.info("otp_verify_success", user_id=result["user_id"])
        return result

    async def sign_in_apple(
        self, identity_token: str, conn: Connection
    ) -> dict[str, Any]:
        """Exchange an Apple identity token for a Supabase session."""
        logger.info("apple_signin_requested")
        try:
            result = await asyncio.to_thread(_sign_in_apple_sync, identity_token)
        except AuthError:
            raise
        except Exception as exc:
            logger.error("apple_signin_failed", error=str(exc))
            raise AuthError("Apple sign-in failed") from exc

        if result["email"]:
            await _ensure_user_exists(conn, result["user_id"], result["email"])
        logger.info("apple_signin_success", user_id=result["user_id"])
        return result

    async def refresh_session(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token using the refresh token."""
        logger.info("token_refresh_requested")
        try:
            result = await asyncio.to_thread(_refresh_session_sync, refresh_token)
        except AuthError:
            raise
        except Exception as exc:
            logger.error("token_refresh_failed", error=str(exc))
            raise AuthError("Token refresh failed") from exc
        logger.info("token_refresh_success")
        return result
