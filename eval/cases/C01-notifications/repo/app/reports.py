"""Operational reporting."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.couriers import name_for
from app.store.models import Shipment


async def shipments_by_courier(session: AsyncSession) -> list[dict]:
    """Every shipment, with the name of the courier carrying it."""
    result = await session.execute(select(Shipment))
    shipments = result.scalars().all()

    return [
        {
            "id": shipment.id,
            "courier": await name_for(session, shipment.courier_id),
            "status": shipment.status,
        }
        for shipment in shipments
    ]
