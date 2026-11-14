from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.warehouse import Warehouse


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Stock(Base):
    """
    Модель товарных остатков на складе
    
    Атрибуты:
        physical_qty: Фактическое физическое количество товара на складе
        reserved_fbs_qty: Количество зарезервированного товара под клиентские заказы FBS
        available_qty: Вычисляемый доступный остаток (физический минус резерв)
    """
    __tablename__ = "stocks"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_product_warehouse"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    physical_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_fbs_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="stocks")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="stocks")

    @property
    def available_qty(self) -> int:
        """Доступное количество товара для резервирования или отгрузки"""
        return max(0, self.physical_qty - self.reserved_fbs_qty)
