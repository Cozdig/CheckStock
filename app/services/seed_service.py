from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.stock import Stock
from app.models.history import OperationLog


class SeedService:
    """Сервис инициализации демонстрационных данных согласно ТЗ CheckStock"""

    @staticmethod
    async def seed_data(session: AsyncSession) -> Dict[str, Any]:
        """
        Заполняет базу данных тестовыми данными:
            Склады: 'Север', 'Юг'
            Товары и стартовые остатки:
                SKU-101 (Органайзер): Север 10, Юг 6
                SKU-102 (Контейнер):  Север 5,  Юг 0
                SKU-103 (Корзина):    Север 0,  Юг 4
        """
        res = await session.execute(select(Product))
        if res.scalars().first():
            return {"status": "already_seeded", "message": "База данных уже содержит данные"}

        north = Warehouse(name="Север", is_active=True)
        south = Warehouse(name="Юг", is_active=True)
        session.add_all([north, south])
        await session.flush()

        products_data = [
            {"sku": "SKU-101", "name": "Органайзер", "north": 10, "south": 6},
            {"sku": "SKU-102", "name": "Контейнер", "north": 5, "south": 0},
            {"sku": "SKU-103", "name": "Корзина", "north": 0, "south": 4},
        ]

        for p_data in products_data:
            p = Product(sku=p_data["sku"], name=p_data["name"])
            session.add(p)
            await session.flush()

            if p_data["north"] > 0:
                s_north = Stock(product_id=p.id, warehouse_id=north.id, physical_qty=p_data["north"], reserved_fbs_qty=0)
                session.add(s_north)
                log_n = OperationLog(
                    operation_type="INCOME",
                    product_id=p.id,
                    to_warehouse_id=north.id,
                    quantity=p_data["north"],
                    destination_desc="Склад Север",
                    comment=f"Стартовый приход {p.sku} ({p_data['north']} шт.) на склад Север"
                )
                session.add(log_n)

            if p_data["south"] > 0:
                s_south = Stock(product_id=p.id, warehouse_id=south.id, physical_qty=p_data["south"], reserved_fbs_qty=0)
                session.add(s_south)
                log_s = OperationLog(
                    operation_type="INCOME",
                    product_id=p.id,
                    to_warehouse_id=south.id,
                    quantity=p_data["south"],
                    destination_desc="Склад Юг",
                    comment=f"Стартовый приход {p.sku} ({p_data['south']} шт.) на склад Юг"
                )
                session.add(log_s)

        await session.commit()
        return {"status": "seeded", "message": "Демонстрационные данные успешно инициализированы"}
