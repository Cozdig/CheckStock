from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.stock import Stock


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    """
    Модель номенклатурной единицы товара (SKU)
    """
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    stocks: Mapped[list["Stock"]] = relationship("Stock", back_populates="product", cascade="all, delete-orphan")
