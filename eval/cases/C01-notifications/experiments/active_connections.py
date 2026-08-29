"""How many connections are still held after work that failed.

Runs the case repository's own `with_session` twenty times against work that
raises, then asks the pool how many connections it has checked out. A session
released in every path leaves none. One released only on success leaks one per
failure, and a pool drains one request at a time until it stops answering.

The last line printed is the measurement, as connections held.
"""

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import AsyncAdaptedQueuePool  # noqa: E402

import app.store.session as store  # noqa: E402
from app.store.models import Base  # noqa: E402

FAILURES = 20


async def main() -> None:
    # A real pool on a real file. An in-memory SQLite engine uses StaticPool,
    # which hands out one connection forever and cannot report a checkout, so
    # a leak would be invisible in exactly the place we are looking for it.
    path = Path("/tmp/augury-active-connections.sqlite")
    path.unlink(missing_ok=True)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=FAILURES + 5,
        max_overflow=0,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    # The module's own session factory, pointed at a database we can inspect.
    store.engine = engine
    store.SessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    print(f"{FAILURES} pieces of work, every one of them raising")

    async def fails(session: AsyncSession) -> None:
        await session.execute(select(text("1")))
        raise RuntimeError("the work did not succeed")

    for _ in range(FAILURES):
        try:
            await store.with_session(fails)
        except RuntimeError:
            pass

    held = engine.pool.checkedout()
    await engine.dispose()
    path.unlink(missing_ok=True)

    print(f"connections still checked out after {FAILURES} failures:")
    print(held)


asyncio.run(main())
