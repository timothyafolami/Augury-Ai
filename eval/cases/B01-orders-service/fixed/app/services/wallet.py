"""Customer wallet balance operations."""

from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet


class InsufficientFunds(Exception):
    """The wallet does not hold enough to cover the debit."""


async def debit(session: AsyncSession, customer_id: int, amount: Decimal) -> Decimal:
    """Take `amount` from a customer's wallet and return the new balance.

    One statement: the check and the write are the same operation, so no
    reader can act on a balance another writer has already spent.
    """
    result = await session.execute(
        update(Wallet)
        .where(Wallet.customer_id == customer_id, Wallet.balance >= amount)
        .values(balance=Wallet.balance - amount)
        .returning(Wallet.balance)
    )
    row = result.first()
    await session.commit()

    if row is None:
        raise InsufficientFunds(f"balance is below {amount}")
    return Decimal(str(row[0]))


async def credit(session: AsyncSession, customer_id: int, amount: Decimal) -> Decimal:
    """Add `amount` to a customer's wallet and return the new balance."""
    result = await session.execute(
        update(Wallet)
        .where(Wallet.customer_id == customer_id)
        .values(balance=Wallet.balance + amount)
        .returning(Wallet.balance)
    )
    await session.commit()
    return Decimal(str(result.scalar_one()))
