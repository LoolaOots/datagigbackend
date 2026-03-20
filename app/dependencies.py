from typing import Annotated, Any

import httpx
import jwt
from jwt import PyJWK
import structlog
from asyncpg import Connection  # type: ignore[import-untyped]
from fastapi import Depends, Header, HTTPException, Request

from app.config import get_settings, Settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------


async def get_db(request: Request) -> Any:  # yields asyncpg Connection
    """Yield an asyncpg connection acquired from app.state.db_pool."""
    async with request.app.state.db_pool.acquire() as conn:
        yield conn


DBConn = Annotated[Connection, Depends(get_db)]


# ---------------------------------------------------------------------------
# Internal secret dependency
# ---------------------------------------------------------------------------


async def require_internal(
    x_internal_secret: Annotated[str, Header()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Validate the x-internal-secret header against INTERNAL_API_SECRET."""
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")


InternalAuth = Annotated[None, Depends(require_internal)]


# ---------------------------------------------------------------------------
# Supabase JWT dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    authorization: Annotated[str, Header()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """
    Verify a Supabase JWT using the cached JWKS stored on app.state.

    The JWKS is fetched once at startup (in lifespan) and cached on
    app.state.jwks.  Falls back to a fresh fetch if the cached keys do not
    contain the required kid.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    kid = header.get("kid")

    # Use cached JWKS; re-fetch if kid is missing
    jwks: dict[str, Any] = getattr(request.app.state, "jwks", {"keys": []})
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    if key_data is None:
        jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
        jwks = resp.json()
        request.app.state.jwks = jwks
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    if key_data is None:
        raise HTTPException(status_code=401, detail="Unknown token key")

    try:
        signing_key = PyJWK(key_data)
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=[signing_key.algorithm_name],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
