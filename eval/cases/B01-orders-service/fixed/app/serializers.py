"""Turning models into response payloads."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.line_item import LineItem
from app.models.order import Order


async def serialize_order(session: AsyncSession, order: Order) -> dict:
    """Render one order, including its line items."""
    result = await session.execute(select(LineItem).where(LineItem.order_id == order.id))
    return _render(order, list(result.scalars().all()))


async def serialize_orders(session: AsyncSession, orders: list[Order]) -> list[dict]:
    """Render many orders in one query, whatever the result set size."""
    ids = [order.id for order in orders]
    result = await session.execute(select(LineItem).where(LineItem.order_id.in_(ids)))

    by_order: dict[int, list[LineItem]] = {}
    for item in result.scalars().all():
        by_order.setdefault(item.order_id, []).append(item)

    return [_render(order, by_order.get(order.id, [])) for order in orders]


def _render(order: Order, items: list[LineItem]) -> dict:
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
