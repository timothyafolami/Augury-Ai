"""Inbound delivery webhooks."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Shipment


async def record_delivery(
    session: AsyncSession, shipment_id: int, delivery_id: str
) -> dict:
    """Mark a shipment delivered and count it toward the courier's total.

    The courier posts this when a parcel is handed over. `delivery_id`
    identifies the delivery event so the caller can correlate its own records.
    """
    result = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one()

    shipment.status = "delivered"
    shipment.delivery_count = shipment.delivery_count + 1
    await session.commit()

    return {"shipment_id": shipment.id, "deliveries": shipment.delivery_count}
