import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg  # type: ignore[import-untyped]
import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import settings
from app.exceptions import register_exception_handlers
from app.logging_config import configure_logging
from app.routers import auth as auth_router
from app.routers import email as email_router
from app.routers import gigs as gigs_router
from app.routers import health, verify
from app.routers import applications as applications_router
from app.routers import profile as profile_router
from app.routers import submissions as submissions_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown tasks."""
    configure_logging()

    # Create asyncpg connection pool
    app.state.db_pool = await asyncpg.create_pool(
        dsn=settings.database_url, min_size=2, max_size=10
    )

    # Pre-fetch and cache Supabase JWKS
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_url, timeout=10.0)
            resp.raise_for_status()
            app.state.jwks = resp.json()
        logger.info("jwks_cached", url=jwks_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("jwks_fetch_failed", url=jwks_url, error=str(exc))
        app.state.jwks = {"keys": []}

    logger.info("app_started", env=settings.app_env)

    yield

    # Shutdown: close DB pool
    await app.state.db_pool.close()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(
        title="DataGigs Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins for now; tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request-ID middleware — binds request_id to structlog context
    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        logger.info("request", method=request.method, path=request.url.path)
        response = await call_next(request)
        logger.info("response", method=request.method, path=request.url.path, status=response.status_code)
        response.headers["x-request-id"] = request_id
        return response

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(health.router)
    app.include_router(verify.router)
    app.include_router(email_router.router)
    app.include_router(auth_router.router)
    app.include_router(gigs_router.router)
    app.include_router(applications_router.router)
    app.include_router(profile_router.router)
    app.include_router(submissions_router.router)

    return app


app: FastAPI = create_app()
