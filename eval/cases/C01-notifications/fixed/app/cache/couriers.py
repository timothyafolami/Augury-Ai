"""Courier reference data."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Courier


async def names_for(session: AsyncSession, courier_ids: list[int]) -> dict[int, str]:
    """Display names for many couriers, in one query."""
    result = await session.execute(select(Courier).where(Courier.id.in_(courier_ids)))
    return {courier.id: courier.name for courier in result.scalars().all()}


async def name_for(session: AsyncSession, courier_id: int) -> str:
    """The display name of one courier."""
    names = await names_for(session, [courier_id])
    return names[courier_id]
