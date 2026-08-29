"""Turning models into response payloads."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.line_item import LineItem


async def serialize_order(session: AsyncSession, order: Order) -> dict:
    """Render one order, including its line items."""
    result = await session.execute(select(LineItem).where(LineItem.order_id == order.id))
    items = result.scalars().all()

    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total": str(order.total),
        "items": [
            {"sku": item.sku, "quantity": item.quantity, "price": str(item.price)}
            for item in items
        ],
    }
