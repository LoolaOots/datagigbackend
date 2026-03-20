import asyncpg  # type: ignore[import-untyped]

from app.config import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:  # type: ignore[type-arg]
    """Create and return an asyncpg connection pool using the provided settings."""
    pool: asyncpg.Pool = await asyncpg.create_pool(  # type: ignore[type-arg]
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
    )
    return pool
