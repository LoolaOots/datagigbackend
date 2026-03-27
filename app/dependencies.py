from typing import Annotated, Any

import httpx
import jwt
import structlog
from asyncpg import Connection  # type: ignore[import-untyped]
from fastapi import Depends, Header, HTTPException, Request
from jwt.algorithms import ECAlgorithm, OKPAlgorithm, RSAAlgorithm

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


def _public_key_from_jwk(key_data: dict[str, Any]) -> tuple[Any, list[str]]:
    """Convert a JWK dict to a (public_key, algorithms) pair based on key type."""
    kty = key_data.get("kty", "")
    match kty:
        case "RSA":
            return RSAAlgorithm.from_jwk(key_data), ["RS256", "RS384", "RS512"]
        case "EC":
            return ECAlgorithm.from_jwk(key_data), ["ES256", "ES384", "ES512"]
        case "OKP":
            return OKPAlgorithm.from_jwk(key_data), ["EdDSA"]
        case _:
            raise HTTPException(status_code=401, detail=f"Unsupported JWK key type: {kty!r}")


async def _fetch_jwks(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


async def get_current_user(
    request: Request,
    authorization: Annotated[str, Header()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """
    Verify a Supabase JWT using JWKS. Handles RSA, EC, and OKP key types.
    JWKS is cached on app.state and re-fetched only when the kid is unknown.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing key ID")

    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"

    jwks: dict[str, Any] = getattr(request.app.state, "jwks", {"keys": []})
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    if key_data is None:
        try:
            jwks = await _fetch_jwks(jwks_url)
        except httpx.HTTPError as exc:
            logger.error("jwks_fetch_failed", url=jwks_url, error=str(exc))
            raise HTTPException(status_code=503, detail="Auth service unavailable") from exc
        request.app.state.jwks = jwks
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    if key_data is None:
        raise HTTPException(status_code=401, detail="Unknown token signing key")

    public_key, algorithms = _public_key_from_jwk(key_data)

    try:
        payload: dict[str, Any] = jwt.decode(
            token, public_key, algorithms=algorithms, audience="authenticated"
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        logger.error("jwt_decode_failed", error=str(exc), error_type=type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token") from exc


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
