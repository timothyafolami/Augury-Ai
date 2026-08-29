"""Health and readiness."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict:
    """Readiness: the database answers."""
    await session.execute(select(1))
    return {"status": "ready"}
