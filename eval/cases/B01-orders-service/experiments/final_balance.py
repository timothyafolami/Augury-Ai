"""What a wallet holds after ten concurrent debits that should empty it.

Runs the case repository's own `debit` from ten concurrent sessions, each
taking 10 from a balance of 100. Correct behaviour leaves 0. Every debit that
reads a stale balance and writes back its own difference silently overwrites
the ones beside it, so what remains is the money that was taken and never
recorded.

Nothing here simulates the defect. The function under measurement is the
function under review; only the concurrency is supplied.

Only InsufficientFunds is caught. An earlier version caught everything, so a
`debit` that raised on every call measured 100.0 -- a healthier-looking number
than the defect's 90.0, from code that could not debit at all. A broken
function must fail the experiment and resolve to Broken, not produce a
flattering measurement.

The last line printed is the measurement, in currency units remaining.
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

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.base import Base  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.wallet import Wallet  # noqa: E402
from app.services.wallet import InsufficientFunds, debit  # noqa: E402

STARTING = Decimal("100.00")
DEBITS = 10
EACH = Decimal("10.00")


async def main() -> None:
    # A file-backed database, because every session must see the same rows.
    path = Path("/tmp/augury-final-balance.sqlite")
    path.unlink(missing_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        session.add(Customer(id=1, email="a@b.c", name="A"))
        session.add(Wallet(customer_id=1, balance=STARTING))
        await session.commit()

    print(f"starting balance {STARTING}, {DEBITS} concurrent debits of {EACH}")

    async def take() -> None:
        # Each request gets its own session, as it would in the service.
        async with sessions() as session:
            try:
                await debit(session, 1, EACH)
            except InsufficientFunds:
                # A refused debit is a correct outcome, not a failure.
                return

    await asyncio.gather(*(take() for _ in range(DEBITS)))

    async with sessions() as session:
        result = await session.execute(select(Wallet).where(Wallet.customer_id == 1))
        remaining = result.scalar_one().balance

    await engine.dispose()
    path.unlink(missing_ok=True)

    print(f"correct final balance would be {STARTING - DEBITS * EACH}; observed:")
    print(float(remaining))


asyncio.run(main())
