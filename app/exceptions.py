import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base application error. Raise subclasses from the service layer."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found", status_code=404)


class AuthError(AppError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


# ---------------------------------------------------------------------------
# FastAPI exception handler functions
# ---------------------------------------------------------------------------


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    logger.error(
        "app_error",
        path=request.url.path,
        status_code=exc.status_code,
        message=exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
