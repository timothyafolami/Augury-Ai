"""How many times one delivery is counted when the courier redelivers.

Runs the case repository's own `record_delivery` three times with the same
`delivery_id`, which is what a courier does when it does not receive an
acknowledgement. A handler that records the identifier it is given counts the
parcel once. One that ignores it counts it every time.

The last line printed is the measurement, as a count of applied effects.
"""

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.handlers.webhook import record_delivery  # noqa: E402
from app.store.models import Base, Courier, Shipment  # noqa: E402

REDELIVERIES = 3


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        session.add(Courier(id=1, name="Parcelforce"))
        session.add(Shipment(id=1, courier_id=1))
        await session.commit()

    print(f"the courier posts the same delivery {REDELIVERIES} times")

    async with sessions() as session:
        for _ in range(REDELIVERIES):
            try:
                await record_delivery(session, shipment_id=1, delivery_id="DEL-1")
            except Exception as error:
                # A handler that refuses the duplicate outright is also correct.
                print(f"redelivery refused: {type(error).__name__}")

    async with sessions() as session:
        result = await session.execute(select(Shipment).where(Shipment.id == 1))
        counted = result.scalar_one().delivery_count

    await engine.dispose()

    print(f"one parcel was delivered once and counted {counted} times:")
    print(counted)


asyncio.run(main())
