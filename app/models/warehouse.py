from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.stock import Stock


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Warehouse(Base):
    """
    Модель склада фулфилмента (ФФ)
    
    Поддерживает мягкое удаление (soft delete) через флаг `is_active`
    При архивации склада физические остатки и история операций сохраняются
    """
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    stocks: Mapped[list["Stock"]] = relationship("Stock", back_populates="warehouse", cascade="all, delete-orphan")
