"""Customer endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.customer import Customer

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/{customer_id}")
async def read_customer(
    customer_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return {"id": customer.id, "email": customer.email, "name": customer.name}
