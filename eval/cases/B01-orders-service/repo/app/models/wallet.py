"""Customer wallet model."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), unique=True, index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
