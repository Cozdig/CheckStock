from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.movement import WarehouseMovement
from app.models.shipment import Shipment
from app.models.history import OperationLog
from app.schemas.stock import MovementOut, ShipmentOut, OperationLogOut


class QueryService:
    """Сервис для выполнения запросов чтения и построения отчетов"""

    @staticmethod
    async def get_movements(session: AsyncSession) -> List[MovementOut]:
        """Возвращает список всех внутренних перемещений между складами"""
        stmt = (
            select(WarehouseMovement)
            .options(
                joinedload(WarehouseMovement.product),
                joinedload(WarehouseMovement.from_warehouse),
                joinedload(WarehouseMovement.to_warehouse),
            )
            .order_by(WarehouseMovement.id.desc())
        )
        res = await session.execute(stmt)
        movements = res.scalars().all()
        return [
            MovementOut(
                id=m.id,
                from_warehouse_id=m.from_warehouse_id,
                from_warehouse_name=m.from_warehouse.name,
                to_warehouse_id=m.to_warehouse_id,
                to_warehouse_name=m.to_warehouse.name,
                product_id=m.product_id,
                sku=m.product.sku,
                product_name=m.product.name,
                quantity=m.quantity,
                status=m.status,
                created_at=m.created_at,
            )
            for m in movements
        ]

    @staticmethod
    async def get_shipments(session: AsyncSession, shipment_type: Optional[str] = None) -> List[ShipmentOut]:
        """Возвращает список внешних отгрузок (FBS / FBO)"""
        stmt = (
            select(Shipment)
            .options(
                joinedload(Shipment.product),
                joinedload(Shipment.warehouse),
            )
            .order_by(Shipment.id.desc())
        )
        if shipment_type:
            stmt = stmt.where(Shipment.shipment_type == shipment_type)
        res = await session.execute(stmt)
        shipments = res.scalars().all()
        return [
            ShipmentOut(
                id=s.id,
                shipment_type=s.shipment_type,
                warehouse_id=s.warehouse_id,
                warehouse_name=s.warehouse.name,
                product_id=s.product_id,
                sku=s.product.sku,
                product_name=s.product.name,
                quantity=s.quantity,
                status=s.status,
                destination=s.destination,
                created_at=s.created_at,
            )
            for s in shipments
        ]

    @staticmethod
    async def get_operation_logs(session: AsyncSession, limit: int = 100) -> List[OperationLogOut]:
        """Возвращает журнал аудита складских операций"""
        stmt = (
            select(OperationLog)
            .options(
                joinedload(OperationLog.product),
                joinedload(OperationLog.from_warehouse),
                joinedload(OperationLog.to_warehouse),
            )
            .order_by(OperationLog.id.desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        logs = res.scalars().all()
        return [
            OperationLogOut(
                id=log.id,
                operation_type=log.operation_type,
                product_sku=log.product.sku if log.product else "-",
                product_name=log.product.name if log.product else "-",
                from_warehouse_name=log.from_warehouse.name if log.from_warehouse else None,
                to_warehouse_name=log.to_warehouse.name if log.to_warehouse else None,
                destination_desc=log.destination_desc,
                quantity=log.quantity,
                comment=log.comment,
                created_at=log.created_at,
            )
            for log in logs
        ]
