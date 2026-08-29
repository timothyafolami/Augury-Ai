"""What the orders listing returns when the database is unavailable.

Calls the case repository's own `list_for_customer` against a session whose
connection has been closed, and reports the status a client would receive.

A broken dependency should surface as a failure. A handler that catches
everything and returns a default turns it into a fast, successful, empty
response: the dashboard stays green, latency improves, and nobody is paged.

The last line printed is the measurement, as an HTTP status code.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "repo"))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.base import Base  # noqa: E402
from app.models.customer import Customer  # noqa: F401, E402  - registers the table
from app.models.line_item import LineItem  # noqa: F401, E402 - registers the table
from app.models.order import Order  # noqa: F401, E402        - registers the table
from app.models.wallet import Wallet  # noqa: F401, E402       - registers the table
from app.repositories.orders import list_for_customer  # noqa: E402


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    print("querying with the database made unavailable")

    async with sessions() as session:
        # Take the store away underneath the call, the way an outage does.
        await engine.dispose()
        await session.close()
        try:
            orders = await list_for_customer(session, customer_id=1)
        except Exception:
            # The failure reached the caller, which is the correct behaviour:
            # a request handler would turn this into a 500.
            print("the failure reached the caller")
            print(500)
            return

    print(f"the call returned {orders!r} and the caller cannot tell it failed")
    print(200)


asyncio.run(main())
