"""Customer wallet balance operations."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet


class InsufficientFunds(Exception):
    """The wallet does not hold enough to cover the debit."""


async def debit(session: AsyncSession, customer_id: int, amount: Decimal) -> Decimal:
    """Take `amount` from a customer's wallet and return the new balance.

    Checks the balance first so we never take a wallet negative.
    """
    result = await session.execute(select(Wallet).where(Wallet.customer_id == customer_id))
    wallet = result.scalar_one()

    if wallet.balance < amount:
        raise InsufficientFunds(f"balance {wallet.balance} is below {amount}")

    wallet.balance = wallet.balance - amount
    await session.commit()
    return wallet.balance


async def credit(session: AsyncSession, customer_id: int, amount: Decimal) -> Decimal:
    """Add `amount` to a customer's wallet and return the new balance."""
    result = await session.execute(select(Wallet).where(Wallet.customer_id == customer_id))
    wallet = result.scalar_one()
    wallet.balance = wallet.balance + amount
    await session.commit()
    return wallet.balance
