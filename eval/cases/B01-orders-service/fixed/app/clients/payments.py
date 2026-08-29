"""Payment gateway client."""

import asyncio
import logging
import random
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = "https://payments.internal/charge"
MAX_ATTEMPTS = 3

# Retries are capped in aggregate, not only per request. Per-request caps do
# nothing at the moment that matters, when every client is retrying at once.
RETRY_BUDGET_RATIO = 0.1
_attempts = 0
_retries = 0


async def charge(customer_id: int, amount: Decimal, idempotency_key: str) -> str:
    """Charge a customer and return the gateway's transaction id."""
    global _attempts, _retries
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt and _retries > max(1, int(_attempts * RETRY_BUDGET_RATIO)):
            break
        _attempts += 1
        if attempt:
            _retries += 1
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
            # Exponential, with full jitter, so retries do not synchronise.
            await asyncio.sleep(0.05 * (2**attempt) * random.random())

    raise RuntimeError(f"payment gateway unavailable: {last_error}")
