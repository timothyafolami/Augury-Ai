"""Price calculation.

FIXME: this is slow and needs optimising before the next sale.
"""

from decimal import Decimal

VAT_RATE = Decimal("0.20")
BULK_THRESHOLD = 10
BULK_DISCOUNT = Decimal("0.05")


def line_total(price: Decimal, quantity: int) -> Decimal:
    """The cost of one line, after any bulk discount."""
    subtotal = price * quantity
    if quantity >= BULK_THRESHOLD:
        subtotal -= subtotal * BULK_DISCOUNT
    return subtotal.quantize(Decimal("0.01"))


def with_vat(amount: Decimal) -> Decimal:
    return (amount * (Decimal("1") + VAT_RATE)).quantize(Decimal("0.01"))
