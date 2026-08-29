"""Order persistence."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order

logger = logging.getLogger(__name__)


async def load(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def list_for_customer(session: AsyncSession, customer_id: int) -> list[Order]:
    """Every order belonging to a customer, newest first.

    Returns an empty list when the customer has no orders.
    """
    try:
        result = await session.execute(
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())
    except Exception:
        logger.exception("could not list orders for customer %s", customer_id)
        return []
