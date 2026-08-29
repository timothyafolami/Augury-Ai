"""Inbound delivery webhooks."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import DeliveryEvent, Shipment


async def record_delivery(
    session: AsyncSession, shipment_id: int, delivery_id: str
) -> dict:
    """Mark a shipment delivered and count it toward the courier's total.

    The delivery identifier is recorded in the same transaction as the effect
    it guards, so a redelivery finds it already there and changes nothing. A
    courier that does not receive an acknowledgement will post again, and
    posting again must not deliver the parcel again.
    """
    seen = await session.execute(
        select(DeliveryEvent).where(DeliveryEvent.delivery_id == delivery_id)
    )
    result = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one()

    if seen.scalar_one_or_none() is not None:
        return {"shipment_id": shipment.id, "deliveries": shipment.delivery_count}

    session.add(DeliveryEvent(delivery_id=delivery_id, shipment_id=shipment_id))
    shipment.status = "delivered"
    shipment.delivery_count = shipment.delivery_count + 1
    await session.commit()

    return {"shipment_id": shipment.id, "deliveries": shipment.delivery_count}
