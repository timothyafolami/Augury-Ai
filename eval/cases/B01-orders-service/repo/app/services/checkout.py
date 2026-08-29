"""Placing an order."""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import payments, shipping
from app.models.line_item import LineItem
from app.models.order import Order
from app.services import wallet


async def place_order(
    session: AsyncSession,
    customer_id: int,
    items: list[dict],
    postcode: str,
) -> Order:
    """Charge the customer and record the order."""
    goods = sum(Decimal(str(item["price"])) * item["quantity"] for item in items)
    weight = sum(int(item.get("weight_grams", 0)) for item in items)
    delivery = await shipping.quote(postcode, weight)
    total = goods + delivery

    await wallet.debit(session, customer_id, total)
    transaction_id = await payments.charge(customer_id, total, str(uuid.uuid4()))

    order = Order(customer_id=customer_id, status="paid", total=total)
    session.add(order)
    await session.flush()

    for item in items:
        session.add(
            LineItem(
                order_id=order.id,
                sku=item["sku"],
                quantity=item["quantity"],
                price=Decimal(str(item["price"])),
            )
        )

    await session.commit()
    return order
