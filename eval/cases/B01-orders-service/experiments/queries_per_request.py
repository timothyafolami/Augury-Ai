"""How many queries one call to the orders list endpoint issues.

Runs the case repository's own `serialize_order` against an in-memory database
holding a known number of orders, and counts the statements SQLAlchemy actually
sends. Nothing is simulated: the code under measurement is the code under
review, and the count is taken from the engine rather than from reading the
source.

The last line printed is the measurement, in queries.
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "repo"))

from sqlalchemy import event, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.base import Base  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.line_item import LineItem  # noqa: E402
from app.models.order import Order  # noqa: E402
from app.models.wallet import Wallet  # noqa: E402
from app.serializers import serialize_order  # noqa: E402

ORDERS = 50
ITEMS_PER_ORDER = 3


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        session.add(Customer(id=1, email="a@b.c", name="A"))
        session.add(Wallet(customer_id=1, balance=Decimal("1000.00")))
        for order_id in range(1, ORDERS + 1):
            session.add(
                Order(id=order_id, customer_id=1, status="paid", total=Decimal("10.00"))
            )
            for index in range(ITEMS_PER_ORDER):
                session.add(
                    LineItem(
                        order_id=order_id,
                        sku=f"SKU-{index}",
                        quantity=1,
                        price=Decimal("3.33"),
                    )
                )
        await session.commit()

    counted = 0

    def count(*_args: object, **_kwargs: object) -> None:
        nonlocal counted
        counted += 1

    print(f"seeded {ORDERS} orders with {ITEMS_PER_ORDER} items each")

    async with sessions() as session:
        # Count only the read path an incoming request would take.
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        result = await session.execute(select(Order).where(Order.customer_id == 1))
        for order in result.scalars().all():
            await serialize_order(session, order)
        event.remove(engine.sync_engine, "before_cursor_execute", count)

    await engine.dispose()

    print(f"statements issued for a {ORDERS}-order listing:")
    print(counted)


asyncio.run(main())
