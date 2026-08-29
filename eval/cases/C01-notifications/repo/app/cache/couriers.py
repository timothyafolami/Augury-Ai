"""Courier reference data."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Courier


async def name_for(session: AsyncSession, courier_id: int) -> str:
    """The display name of a courier.

    Reference data, so this is looked up wherever a name is needed.
    """
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    return str(result.scalar_one().name)
