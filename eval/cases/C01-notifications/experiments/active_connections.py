"""How many failing operations the pool survives.

Runs the case repository's own `with_session` against work that raises, using
the pool configuration the repository actually declares, and counts how many
operations complete before the pool refuses to hand out a connection.

A session released on every path returns its connection each time, so failures
cost nothing and the count is the number attempted. A session released only on
success leaks one per failure, and the pool is empty after as many failures as
it has connections.

An earlier version took a `checkedout()` snapshot instead. That measured
CPython's garbage collector: the unreachable sessions were reclaimed mid-run and
their connections terminated, so the same code reported 6, 20 or 0 depending on
GC configuration, and one `gc.collect()` made the leaking and the correct
version identical. Exhaustion is a property of the pool and cannot be collected
away.

The last line printed is the measurement, as operations completed.
"""

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import TimeoutError as PoolTimeout  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import AsyncAdaptedQueuePool  # noqa: E402

import app.store.session as store  # noqa: E402
from app.store.models import Base  # noqa: E402

ATTEMPTS = 40
POOL_SIZE = 10


async def main() -> None:
    path = Path("/tmp/augury-active-connections.sqlite")
    path.unlink(missing_ok=True)

    # The pool the repository declares, not a generous one. A pool with room
    # to spare can absorb every leak the experiment creates and report nothing.
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=POOL_SIZE,
        max_overflow=0,
        pool_timeout=1,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    store.engine = engine
    store.SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print(f"a pool of {POOL_SIZE}, and {ATTEMPTS} pieces of work that all raise")

    async def fails(session: AsyncSession) -> None:
        await session.execute(select(text("1")))
        raise RuntimeError("the work did not succeed")

    completed = 0
    for _ in range(ATTEMPTS):
        try:
            await store.with_session(fails)
        except RuntimeError:
            completed += 1
        except PoolTimeout:
            print("the pool refused to hand out a connection")
            break
        except Exception:
            break

    await engine.dispose()
    path.unlink(missing_ok=True)

    print(f"operations completed before the pool ran out:")
    print(completed)


asyncio.run(main())
