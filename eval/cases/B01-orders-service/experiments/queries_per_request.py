"""How many queries one call to the orders list endpoint issues.

Calls the case repository's own `list_orders` endpoint function against a
database holding a known number of orders, and counts the statements
SQLAlchemy actually sends. The count is taken at the engine rather than
inferred from reading the source.

An earlier version built its own loop over its own query and called
`serialize_order` directly. That measured the experiment, not the endpoint: a
repository whose list path had been fixed to batch its loads still reported the
same 51, because the N+1 being counted was the one this file wrote. The
endpoint is now called as a request would call it.

The last line printed is the measurement, in queries.
"""

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

# The repository under measurement. Overridable so the same experiment can be
# run against a remediated copy: an experiment that reports the same number
# either way is not measuring the defect, and tests/test_experiments_
# discriminate.py proves each one does by pointing this at the fixed version.
REPO = Path(os.environ.get("AUGURY_CASE_REPO", Path(__file__).resolve().parent.parent / "repo"))
sys.path.insert(0, str(REPO))

from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.base import Base  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.line_item import LineItem  # noqa: E402
from app.models.order import Order  # noqa: E402
from app.models.wallet import Wallet  # noqa: E402
from app.api.orders import list_orders  # noqa: E402

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
        # Exactly what a GET /orders?customer_id=1 request runs.
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        payload = await list_orders(customer_id=1, session=session)
        event.remove(engine.sync_engine, "before_cursor_execute", count)

    print(f"the endpoint returned {len(payload)} orders")

    await engine.dispose()

    print(f"statements issued for a {ORDERS}-order listing:")
    print(counted)


asyncio.run(main())
