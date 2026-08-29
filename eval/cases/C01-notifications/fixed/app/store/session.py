"""Database sessions for the worker."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://app:app@db:5432/app")

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=0)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def with_session(work: object) -> object:
    """Run `work` against a session and return its result.

    The session is released on every path. Releasing it only on success leaks
    a connection per failure, which drains the pool one request at a time and
    shows up as a service that slowly stops answering.
    """
    async with SessionLocal() as session:
        return await work(session)  # type: ignore[operator]
