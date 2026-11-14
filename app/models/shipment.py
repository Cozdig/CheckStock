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


class Shipment(Base):
    """
    Модель внешней отгрузки (FBS / FBO)
    
    Типы отгрузок:
        - FBS:
            Статусы: RESERVED (товар заблокирован) -> SHIPPED_TO_CLIENT (в пути к клиенту) -> DELIVERED (вручен)
        - FBO:
            Статусы: SHIPPED_TO_MP (в пути на склад маркетплейса) -> RECEIVED_BY_MP (принят маркетплейсом)
    """
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shipment_type: Mapped[str] = mapped_column(String(10), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    destination: Mapped[str] = mapped_column(String(150), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    product: Mapped["Product"] = relationship("Product")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse")
