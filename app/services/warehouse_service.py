from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.warehouse import Warehouse
from app.models.stock import Stock
from app.services.exceptions import BusinessLogicException


class WarehouseService:
    """Сервис управления складами фулфилмента (ФФ)"""

    @staticmethod
    async def get_all(session: AsyncSession, only_active: bool = False) -> List[Warehouse]:
        """Возвращает список складов (с возможностью фильтрации по активности)"""
        stmt = select(Warehouse).order_by(Warehouse.id)
        if only_active:
            stmt = stmt.where(Warehouse.is_active == True)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def create(session: AsyncSession, name: str) -> Warehouse:
        """Создает новый склад или восстанавливает ранее архивированный с тем же именем"""
        name = name.strip()
        existing = (await session.execute(select(Warehouse).where(Warehouse.name == name))).scalar_one_or_none()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                await session.commit()
                await session.refresh(existing)
                return existing
            raise BusinessLogicException(f"Склад с именем '{name}' уже существует")

        wh = Warehouse(name=name, is_active=True)
        session.add(wh)
        await session.commit()
        await session.refresh(wh)
        return wh

    @staticmethod
    async def rename(session: AsyncSession, warehouse_id: int, new_name: str) -> Warehouse:
        """Переименовывает склад с проверкой на уникальность имени"""
        new_name = new_name.strip()
        wh = await session.get(Warehouse, warehouse_id)
        if not wh:
            raise BusinessLogicException("Склад не найден")

        existing = (await session.execute(
            select(Warehouse).where(Warehouse.name == new_name, Warehouse.id != warehouse_id)
        )).scalar_one_or_none()
        if existing:
            raise BusinessLogicException(f"Склад с именем '{new_name}' уже существует")

        wh.name = new_name
        await session.commit()
        await session.refresh(wh)
        return wh

    @staticmethod
    async def delete(session: AsyncSession, warehouse_id: int) -> Dict[str, Any]:
        """
        Выполняет мягкое удаление (soft delete) склада фулфилмента
        
        Требование ТЗ:
            'При удалении сохраните остатки и историю. Покажите, где числится товар.'
        Склад помечается неактивным (is_active = False), но записи остатков и журнал операций
        остаются нетронутыми
        """
        wh = await session.get(Warehouse, warehouse_id)
        if not wh:
            raise BusinessLogicException("Склад не найден")

        stocks_res = await session.execute(
            select(Stock).where(Stock.warehouse_id == warehouse_id, Stock.physical_qty > 0)
        )
        stocks_with_items = stocks_res.scalars().all()
        has_remaining_stock = len(stocks_with_items) > 0
        total_remaining_items = sum(s.physical_qty for s in stocks_with_items)

        wh.is_active = False
        await session.commit()
        await session.refresh(wh)

        return {
            "warehouse_id": wh.id,
            "warehouse_name": wh.name,
            "is_active": wh.is_active,
            "has_remaining_stock": has_remaining_stock,
            "remaining_items_count": total_remaining_items,
            "message": (
                f"Склад '{wh.name}' переведён в архив. "
                + (f"Внимание: на складе числится {total_remaining_items} ед. товара! Остатки и история сохранены."
                   if has_remaining_stock else "Остатки нулевые, история операций сохранена.")
            )
        }
