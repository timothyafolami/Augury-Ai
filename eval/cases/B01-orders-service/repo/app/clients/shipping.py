"""Shipping rate lookup."""

from decimal import Decimal

import httpx

RATES_URL = "https://shipping.internal/rates"


async def quote(postcode: str, weight_grams: int) -> Decimal:
    """Ask the shipping provider what delivery will cost."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            RATES_URL, params={"postcode": postcode, "weight": weight_grams}
        )
        response.raise_for_status()
        return Decimal(str(response.json()["amount"]))
