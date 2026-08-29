"""How many queries one operational report issues.

Calls the case repository's own `shipments_by_courier` against a database
holding a known number of shipments carried by two couriers, and counts the
statements SQLAlchemy sends. Two couriers means two names; anything that scales
with the shipment count is resolving the same name repeatedly.

The last line printed is the measurement, in queries.
"""

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.reports import shipments_by_courier  # noqa: E402
from app.store.models import Base, Courier, Shipment  # noqa: E402

SHIPMENTS = 40
COURIERS = 2


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        for courier_id in range(1, COURIERS + 1):
            session.add(Courier(id=courier_id, name=f"Courier {courier_id}"))
        for shipment_id in range(1, SHIPMENTS + 1):
            session.add(
                Shipment(id=shipment_id, courier_id=(shipment_id % COURIERS) + 1)
            )
        await session.commit()

    counted = 0

    def count(*_args: object, **_kwargs: object) -> None:
        nonlocal counted
        counted += 1

    print(f"{SHIPMENTS} shipments carried by {COURIERS} couriers")

    async with sessions() as session:
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        rows = await shipments_by_courier(session)
        event.remove(engine.sync_engine, "before_cursor_execute", count)

    await engine.dispose()

    print(f"the report returned {len(rows)} rows using:")
    print(counted)


asyncio.run(main())
