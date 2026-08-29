"""Order model."""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    total: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(default="pending")
