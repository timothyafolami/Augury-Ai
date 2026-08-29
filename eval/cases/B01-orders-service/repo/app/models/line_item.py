"""Order line item model."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    sku: Mapped[str] = mapped_column(index=True)
    quantity: Mapped[int] = mapped_column()
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
