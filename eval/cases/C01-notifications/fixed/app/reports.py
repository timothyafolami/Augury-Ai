"""Operational reporting."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.couriers import names_for
from app.store.models import Shipment


async def shipments_by_courier(session: AsyncSession) -> list[dict]:
    """Every shipment, with the name of the courier carrying it.

    Two queries whatever the shipment count: there are only ever as many names
    as there are couriers.
    """
    result = await session.execute(select(Shipment))
    shipments = list(result.scalars().all())
    names = await names_for(session, [shipment.courier_id for shipment in shipments])

    return [
        {
            "id": shipment.id,
            "courier": names[shipment.courier_id],
            "status": shipment.status,
        }
        for shipment in shipments
    ]
