"""Order lookup API."""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Order

app = FastAPI(title="orders")


@app.get("/orders/{order_id}")
async def read_order(order_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": order.id, "total": order.total, "status": order.status}


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(select(1))
    return {"status": "ok"}
