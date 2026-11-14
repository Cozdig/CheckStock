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


class OperationLog(Base):
    """
    Журнал аудита всех складских операций (Event Log / Ledger)
    
    Фиксирует тип операции, участвующие склады, количество товара,
    описание назначения и ключ идемпотентности для предотвращения дублей
    """
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    from_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    to_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    destination_desc: Mapped[str] = mapped_column(String(200), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    product: Mapped["Product"] = relationship("Product")
    from_warehouse: Mapped["Warehouse"] = relationship("Warehouse", foreign_keys=[from_warehouse_id])
    to_warehouse: Mapped["Warehouse"] = relationship("Warehouse", foreign_keys=[to_warehouse_id])
