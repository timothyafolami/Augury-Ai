"""Payment gateway client."""

import asyncio
import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = "https://payments.internal/charge"
MAX_ATTEMPTS = 3


async def charge(customer_id: int, amount: Decimal, idempotency_key: str) -> str:
    """Charge a customer and return the gateway's transaction id.

    Retries on transient gateway failures so a blip does not fail the order.
    """
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    GATEWAY_URL,
                    json={"customer_id": customer_id, "amount": str(amount)},
                    headers={"Idempotency-Key": idempotency_key},
                )
                response.raise_for_status()
                return str(response.json()["transaction_id"])
        except httpx.HTTPError as error:
            last_error = error
            logger.warning("charge attempt %s failed: %s", attempt + 1, error)
            await asyncio.sleep(0.5)

    raise RuntimeError(f"payment gateway unavailable after {MAX_ATTEMPTS} attempts: {last_error}")
