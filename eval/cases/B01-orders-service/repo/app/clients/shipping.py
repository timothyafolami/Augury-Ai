"""Shipping rate lookup."""

from decimal import Decimal

import httpx

RATES_URL = "https://shipping.internal/rates"


async def quote(postcode: str, weight_grams: int) -> Decimal:
    """Ask the shipping provider what delivery will cost.

    The provider is slow to warm up under load, so we let it take as long as
    it needs rather than failing a checkout on a transient stall.
    """
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.get(
            RATES_URL, params={"postcode": postcode, "weight": weight_grams}
        )
        response.raise_for_status()
        return Decimal(str(response.json()["amount"]))
