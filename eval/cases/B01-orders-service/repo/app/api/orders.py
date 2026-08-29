"""Order endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories.orders import list_for_customer, load
from app.serializers import serialize_order

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}")
async def read_order(order_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    order = await load(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return await serialize_order(session, order)


@router.get("")
async def list_orders(
    customer_id: int, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Every order for a customer, newest first."""
    orders = await list_for_customer(session, customer_id)
    return [await serialize_order(session, order) for order in orders]
