"""The notification worker.

Takes events from the inbox, records the delivery they describe, and keeps
going. Started by the container.
"""

import asyncio
import logging

from app.handlers.webhook import record_delivery
from app.queue import inbox
from app.store.session import with_session

logger = logging.getLogger(__name__)


async def handle(event: dict) -> None:
    """Record one delivery event."""

    async def work(session: object) -> object:
        return await record_delivery(
            session,  # type: ignore[arg-type]
            shipment_id=int(event["shipment_id"]),
            delivery_id=str(event["delivery_id"]),
        )

    result = await with_session(work)
    logger.info("recorded %s", result)


async def run() -> None:
    """Drain the inbox forever."""
    while True:
        await handle(await inbox.take())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
