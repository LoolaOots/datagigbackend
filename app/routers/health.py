import sys

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Simple liveness check — no auth required."""
    return {"status": "ok", "python": sys.version}
