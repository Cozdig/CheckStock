from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.warehouse import Warehouse


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WarehouseMovement(Base):
    """
    Модель внутреннего перемещения товара между складами фулфилмента (ФФ)
    
    Статусы перемещения:
        - IN_TRANSIT: Товар покинул склад отправления и находится в пути
        - RECEIVED: Товар успешно принят на складе назначения
        - CANCELLED: Перемещение отменено
    """
    __tablename__ = "warehouse_movements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    from_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    to_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="IN_TRANSIT", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    product: Mapped["Product"] = relationship("Product")
    from_warehouse: Mapped["Warehouse"] = relationship("Warehouse", foreign_keys=[from_warehouse_id])
    to_warehouse: Mapped["Warehouse"] = relationship("Warehouse", foreign_keys=[to_warehouse_id])
