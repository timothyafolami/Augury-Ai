"""Inbound delivery webhooks."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import DeliveryEvent, Shipment


async def record_delivery(
    session: AsyncSession, shipment_id: int, delivery_id: str
) -> dict:
    """Mark a shipment delivered and count it toward the courier's total.

    The delivery identifier is written first and the unique index decides. A
    check followed by a write is the same race one level up: two redeliveries
    can both find nothing and both proceed, which is exactly the defect this
    exists to prevent. Letting the constraint arbitrate means only one writer
    can win, whatever the interleaving.
    """
    result = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one()

    session.add(DeliveryEvent(delivery_id=delivery_id, shipment_id=shipment_id))
    try:
        await session.flush()
    except IntegrityError:
        # Already recorded. The parcel was delivered once and is counted once.
        await session.rollback()
        refreshed = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
        current = refreshed.scalar_one()
        return {"shipment_id": current.id, "deliveries": current.delivery_count}

    shipment.status = "delivered"
    shipment.delivery_count = shipment.delivery_count + 1
    await session.commit()

    return {"shipment_id": shipment.id, "deliveries": shipment.delivery_count}
