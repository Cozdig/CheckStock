from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.stock import Stock
from app.models.movement import WarehouseMovement
from app.models.shipment import Shipment
from app.models.history import OperationLog
from app.schemas.stock import ProductStockOverview, StockItemOut
from app.services.exceptions import BusinessLogicException, StockShortageException


class StockService:
    """Сервис управления товарными остатками, перемещениями и отгрузками"""

    @staticmethod
    async def get_or_create_stock(session: AsyncSession, product_id: int, warehouse_id: int) -> Stock:
        """
        Возвращает запись остатка для пары (товар, склад) либо создает новую с нулевыми значениями
        """
        stmt = select(Stock).where(Stock.product_id == product_id, Stock.warehouse_id == warehouse_id)
        res = await session.execute(stmt)
        stock = res.scalar_one_or_none()
        if not stock:
            stock = Stock(product_id=product_id, warehouse_id=warehouse_id, physical_qty=0, reserved_fbs_qty=0)
            session.add(stock)
            await session.flush()
        return stock

    @staticmethod
    async def get_overview(session: AsyncSession) -> List[ProductStockOverview]:
        """
        Формирует агрегированную сводку остатков по каждому товару и складу,
        а также вычисляет товары, находящиеся в пути (между ФФ, по FBO и по FBS)
        """
        products_res = await session.execute(select(Product).order_by(Product.id))
        products = products_res.scalars().all()

        warehouses_res = await session.execute(select(Warehouse).order_by(Warehouse.id))
        warehouses = warehouses_res.scalars().all()

        stocks_res = await session.execute(select(Stock))
        all_stocks = stocks_res.scalars().all()
        stock_map = {(s.product_id, s.warehouse_id): s for s in all_stocks}

        # Товары в пути между складами фулфилмента
        movements_res = await session.execute(
            select(
                WarehouseMovement.product_id,
                func.coalesce(func.sum(WarehouseMovement.quantity), 0).label("qty")
            )
            .where(WarehouseMovement.status == "IN_TRANSIT")
            .group_by(WarehouseMovement.product_id)
        )
        movements_in_transit = {row.product_id: row.qty for row in movements_res.all()}

        # Товары в пути по FBO (отправлены на склад маркетплейса)
        fbo_res = await session.execute(
            select(
                Shipment.product_id,
                func.coalesce(func.sum(Shipment.quantity), 0).label("qty")
            )
            .where(Shipment.shipment_type == "FBO", Shipment.status == "SHIPPED_TO_MP")
            .group_by(Shipment.product_id)
        )
        fbo_in_transit = {row.product_id: row.qty for row in fbo_res.all()}

        # Товары в пути по FBS (отправлены покупателю)
        fbs_res = await session.execute(
            select(
                Shipment.product_id,
                func.coalesce(func.sum(Shipment.quantity), 0).label("qty")
            )
            .where(Shipment.shipment_type == "FBS", Shipment.status == "SHIPPED_TO_CLIENT")
            .group_by(Shipment.product_id)
        )
        fbs_in_transit = {row.product_id: row.qty for row in fbs_res.all()}

        overview: List[ProductStockOverview] = []
        for p in products:
            stocks_by_wh: List[StockItemOut] = []
            total_physical = 0
            total_reserved = 0
            total_available = 0

            for wh in warehouses:
                s = stock_map.get((p.id, wh.id))
                phys = s.physical_qty if s else 0
                resv = s.reserved_fbs_qty if s else 0
                avail = max(0, phys - resv)

                stocks_by_wh.append(StockItemOut(
                    warehouse_id=wh.id,
                    warehouse_name=wh.name,
                    warehouse_is_active=wh.is_active,
                    physical_qty=phys,
                    reserved_fbs_qty=resv,
                    available_qty=avail
                ))

                total_physical += phys
                total_reserved += resv
                total_available += avail

            overview.append(ProductStockOverview(
                product_id=p.id,
                sku=p.sku,
                product_name=p.name,
                stocks_by_warehouse=stocks_by_wh,
                total_physical=total_physical,
                total_reserved_fbs=total_reserved,
                total_available=total_available,
                in_transit_between_wh=movements_in_transit.get(p.id, 0),
                in_transit_fbo=fbo_in_transit.get(p.id, 0),
                in_transit_fbs=fbs_in_transit.get(p.id, 0)
            ))

        return overview

    @staticmethod
    async def add_income(
        session: AsyncSession, warehouse_id: int, product_id: int, quantity: int, comment: Optional[str] = None
    ) -> Stock:
        """
        Оформляет приход товара на склад, увеличивая физический остаток и логируя операцию
        """
        if quantity <= 0:
            raise BusinessLogicException("Количество прихода должно быть строго положительным")

        wh = await session.get(Warehouse, warehouse_id)
        if not wh:
            raise BusinessLogicException("Указанный склад не существует")
        if not wh.is_active:
            raise BusinessLogicException(f"Склад '{wh.name}' находится в архиве, приход невозможен")

        prod = await session.get(Product, product_id)
        if not prod:
            raise BusinessLogicException("Товар не найден")

        stock = await StockService.get_or_create_stock(session, product_id, warehouse_id)
        stock.physical_qty += quantity

        log = OperationLog(
            operation_type="INCOME",
            product_id=product_id,
            to_warehouse_id=warehouse_id,
            quantity=quantity,
            destination_desc=f"Склад {wh.name}",
            comment=comment or f"Приход {quantity} ед. {prod.sku} на склад {wh.name}"
        )
        session.add(log)
        await session.commit()
        await session.refresh(stock)
        return stock

    @staticmethod
    async def check_availability_and_alternatives(
        session: AsyncSession, product_id: int, target_wh_id: int, requested_qty: int
    ) -> None:
        """
        Проверяет наличие свободного остатка на целевом складе
        При нехватке анализирует другие активные склады сети и выбрасывает StockShortageException
        с рекомендацией по внутреннему перемещению
        """
        wh = await session.get(Warehouse, target_wh_id)
        prod = await session.get(Product, product_id)
        if not wh or not prod:
            raise BusinessLogicException("Склад или товар не найден")

        stock = await StockService.get_or_create_stock(session, product_id, target_wh_id)
        available_here = stock.available_qty

        if available_here < requested_qty:
            stmt = (
                select(Stock, Warehouse)
                .join(Warehouse, Stock.warehouse_id == Warehouse.id)
                .where(
                    Stock.product_id == product_id,
                    Stock.warehouse_id != target_wh_id,
                    Warehouse.is_active == True
                )
            )
            res = await session.execute(stmt)
            alternatives = []
            other_available_sum = 0
            for s, w in res.all():
                avail = s.available_qty
                if avail > 0:
                    alternatives.append({"warehouse_id": w.id, "warehouse_name": w.name, "available_qty": avail})
                    other_available_sum += avail

            total_available = available_here + other_available_sum
            diff = requested_qty - available_here

            if total_available >= requested_qty:
                alt_str = ", ".join([f"'{a['warehouse_name']}': {a['available_qty']} шт." for a in alternatives])
                msg = (
                    f"Нехватка товара {prod.sku} на складе '{wh.name}': запрошено {requested_qty} шт., "
                    f"доступно только {available_here} шт. (не хватает {diff} шт.). "
                    f"Однако суммарно по сети доступно {total_available} шт. ({alt_str}). "
                    f"Рекомендуется оформить перемещение между складами!"
                )
            else:
                msg = (
                    f"Нехватка товара {prod.sku} по всей сети: запрошено {requested_qty} шт., "
                    f"доступно на '{wh.name}' {available_here} шт., суммарно по всем складам {total_available} шт."
                )

            raise StockShortageException(
                message=msg,
                product_id=product_id,
                sku=prod.sku,
                requested_qty=requested_qty,
                available_here=available_here,
                total_available=total_available,
                alternatives=alternatives
            )

    @staticmethod
    async def create_movement(
        session: AsyncSession, from_wh_id: int, to_wh_id: int, product_id: int, quantity: int, idempotency_key: Optional[str] = None
    ) -> WarehouseMovement:
        """
        Инициирует перемещение товара между складами
        Списывает физический остаток со склада-отправителя и переводит товар в статус IN_TRANSIT
        """
        if from_wh_id == to_wh_id:
            raise BusinessLogicException("Склад отправления и назначения не могут совпадать")
        if quantity <= 0:
            raise BusinessLogicException("Количество перемещения должно быть строго положительным")

        if idempotency_key:
            stmt = select(WarehouseMovement).where(WarehouseMovement.idempotency_key == idempotency_key)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing

        from_wh = await session.get(Warehouse, from_wh_id)
        to_wh = await session.get(Warehouse, to_wh_id)
        if not from_wh or not to_wh:
            raise BusinessLogicException("Один из складов не найден")

        await StockService.check_availability_and_alternatives(session, product_id, from_wh_id, quantity)

        from_stock = await StockService.get_or_create_stock(session, product_id, from_wh_id)
        from_stock.physical_qty -= quantity

        prod = await session.get(Product, product_id)
        movement = WarehouseMovement(
            product_id=product_id,
            from_warehouse_id=from_wh_id,
            to_warehouse_id=to_wh_id,
            quantity=quantity,
            status="IN_TRANSIT",
            idempotency_key=idempotency_key
        )
        session.add(movement)
        await session.flush()

        log = OperationLog(
            operation_type="MOVEMENT_SEND",
            product_id=product_id,
            from_warehouse_id=from_wh_id,
            to_warehouse_id=to_wh_id,
            quantity=quantity,
            destination_desc=f"В пути на {to_wh.name}",
            comment=f"Отправлено перемещение {prod.sku} ({quantity} шт.) из {from_wh.name} в {to_wh.name}",
            idempotency_key=idempotency_key
        )
        session.add(log)
        await session.commit()
        await session.refresh(movement)
        return movement

    @staticmethod
    async def receive_movement(
        session: AsyncSession, movement_id: int, idempotency_key: Optional[str] = None
    ) -> WarehouseMovement:
        """
        Принимает товар на складе назначения, оприходуя его на остаток
        Операция идемпотентна: повторные вызовы не производят повторного зачисления
        """
        movement = await session.get(WarehouseMovement, movement_id)
        if not movement:
            raise BusinessLogicException("Перемещение не найдено")

        if movement.status == "RECEIVED":
            return movement

        if movement.status != "IN_TRANSIT":
            raise BusinessLogicException(f"Невозможно принять перемещение в текущем статусе: {movement.status}")

        to_stock = await StockService.get_or_create_stock(session, movement.product_id, movement.to_warehouse_id)
        to_stock.physical_qty += movement.quantity
        movement.status = "RECEIVED"

        prod = await session.get(Product, movement.product_id)
        to_wh = await session.get(Warehouse, movement.to_warehouse_id)
        from_wh = await session.get(Warehouse, movement.from_warehouse_id)

        log = OperationLog(
            operation_type="MOVEMENT_RECEIVE",
            product_id=movement.product_id,
            from_warehouse_id=movement.from_warehouse_id,
            to_warehouse_id=movement.to_warehouse_id,
            quantity=movement.quantity,
            destination_desc=f"Склад {to_wh.name}",
            comment=f"Принято перемещение {prod.sku} ({movement.quantity} шт.) на складе {to_wh.name} от {from_wh.name}",
            idempotency_key=idempotency_key
        )
        session.add(log)
        await session.commit()
        await session.refresh(movement)
        return movement

    @staticmethod
    async def reserve_fbs(
        session: AsyncSession, warehouse_id: int, product_id: int, quantity: int, idempotency_key: Optional[str] = None
    ) -> Shipment:
        """
        Блокирует товар под заказ FBS в резерве склада, не уменьшая физический остаток
        """
        if quantity <= 0:
            raise BusinessLogicException("Количество должно быть строго положительным")

        if idempotency_key:
            stmt = select(Shipment).where(Shipment.idempotency_key == idempotency_key)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing

        await StockService.check_availability_and_alternatives(session, product_id, warehouse_id, quantity)

        stock = await StockService.get_or_create_stock(session, product_id, warehouse_id)
        stock.reserved_fbs_qty += quantity

        wh = await session.get(Warehouse, warehouse_id)
        prod = await session.get(Product, product_id)

        shipment = Shipment(
            shipment_type="FBS",
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=quantity,
            status="RESERVED",
            destination="Клиент (FBS)",
            idempotency_key=idempotency_key
        )
        session.add(shipment)
        await session.flush()

        log = OperationLog(
            operation_type="FBS_RESERVE",
            product_id=product_id,
            from_warehouse_id=warehouse_id,
            quantity=quantity,
            destination_desc="Резерв под заказ клиента",
            comment=f"Зарезервировано {quantity} шт. {prod.sku} на складе {wh.name} под заказ FBS",
            idempotency_key=idempotency_key
        )
        session.add(log)
        await session.commit()
        await session.refresh(shipment)
        return shipment

    @staticmethod
    async def cancel_fbs_reserve(session: AsyncSession, shipment_id: int) -> Shipment:
        """
        Отменяет резерв FBS, возвращая товар в пул доступного остатка
        """
        shipment = await session.get(Shipment, shipment_id)
        if not shipment or shipment.shipment_type != "FBS":
            raise BusinessLogicException("Заказ FBS не найден")

        if shipment.status == "CANCELLED":
            return shipment

        if shipment.status != "RESERVED":
            raise BusinessLogicException(f"Отменить можно только зарезервированный заказ (текущий статус: {shipment.status})")

        stock = await StockService.get_or_create_stock(session, shipment.product_id, shipment.warehouse_id)
        stock.reserved_fbs_qty = max(0, stock.reserved_fbs_qty - shipment.quantity)
        shipment.status = "CANCELLED"

        prod = await session.get(Product, shipment.product_id)
        wh = await session.get(Warehouse, shipment.warehouse_id)

        log = OperationLog(
            operation_type="FBS_CANCEL_RESERVE",
            product_id=shipment.product_id,
            from_warehouse_id=shipment.warehouse_id,
            quantity=shipment.quantity,
            destination_desc=f"Склад {wh.name}",
            comment=f"Отменен резерв FBS на {shipment.quantity} шт. {prod.sku} на складе {wh.name}"
        )
        session.add(log)
        await session.commit()
        await session.refresh(shipment)
        return shipment

    @staticmethod
    async def ship_fbs(session: AsyncSession, shipment_id: int, idempotency_key: Optional[str] = None) -> Shipment:
        """
        Оформляет отправку заказа FBS: одновременно списывает физический остаток и резерв
        Товар переходит в статус SHIPPED_TO_CLIENT (едет к покупателю)
        """
        shipment = await session.get(Shipment, shipment_id)
        if not shipment or shipment.shipment_type != "FBS":
            raise BusinessLogicException("Заказ FBS не найден")

        if shipment.status == "SHIPPED_TO_CLIENT":
            return shipment

        if shipment.status != "RESERVED":
            raise BusinessLogicException(f"Отправить можно только зарезервированный заказ (текущий статус: {shipment.status})")

        stock = await StockService.get_or_create_stock(session, shipment.product_id, shipment.warehouse_id)
        stock.physical_qty = max(0, stock.physical_qty - shipment.quantity)
        stock.reserved_fbs_qty = max(0, stock.reserved_fbs_qty - shipment.quantity)
        shipment.status = "SHIPPED_TO_CLIENT"

        prod = await session.get(Product, shipment.product_id)
        wh = await session.get(Warehouse, shipment.warehouse_id)

        log = OperationLog(
            operation_type="FBS_SHIP",
            product_id=shipment.product_id,
            from_warehouse_id=shipment.warehouse_id,
            quantity=shipment.quantity,
            destination_desc="В пути к клиенту (FBS)",
            comment=f"Заказ FBS отправлен покупателю: списано {shipment.quantity} шт. {prod.sku} со склада {wh.name}",
            idempotency_key=idempotency_key
        )
        session.add(log)
        await session.commit()
        await session.refresh(shipment)
        return shipment

    @staticmethod
    async def deliver_fbs(session: AsyncSession, shipment_id: int) -> Shipment:
        """
        Фиксирует успешное вручение заказа клиенту
        """
        shipment = await session.get(Shipment, shipment_id)
        if not shipment or shipment.shipment_type != "FBS":
            raise BusinessLogicException("Заказ FBS не найден")

        if shipment.status == "DELIVERED":
            return shipment

        if shipment.status != "SHIPPED_TO_CLIENT":
            raise BusinessLogicException(f"Вручить можно только отправленный заказ (текущий статус: {shipment.status})")

        shipment.status = "DELIVERED"
        await session.commit()
        await session.refresh(shipment)
        return shipment

    @staticmethod
    async def ship_fbo(
        session: AsyncSession,
        warehouse_id: int,
        product_id: int,
        quantity: int,
        destination: str = "Склад маркетплейса (FBO)",
        idempotency_key: Optional[str] = None
    ) -> Shipment:
        """
        Отгружает партию товара по схеме FBO
        Товар покидает склад (уменьшается физический остаток) и переходит в статус SHIPPED_TO_MP
        """
        if quantity <= 0:
            raise BusinessLogicException("Количество должно быть строго положительным")

        if idempotency_key:
            stmt = select(Shipment).where(Shipment.idempotency_key == idempotency_key)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing

        await StockService.check_availability_and_alternatives(session, product_id, warehouse_id, quantity)

        stock = await StockService.get_or_create_stock(session, product_id, warehouse_id)
        stock.physical_qty -= quantity

        wh = await session.get(Warehouse, warehouse_id)
        prod = await session.get(Product, product_id)

        shipment = Shipment(
            shipment_type="FBO",
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=quantity,
            status="SHIPPED_TO_MP",
            destination=destination or "Склад маркетплейса (FBO)",
            idempotency_key=idempotency_key
        )
        session.add(shipment)
        await session.flush()

        log = OperationLog(
            operation_type="FBO_SHIP",
            product_id=product_id,
            from_warehouse_id=warehouse_id,
            quantity=quantity,
            destination_desc=f"В пути на {shipment.destination}",
            comment=f"Отгружена поставка FBO ({quantity} шт. {prod.sku}) со склада {wh.name}",
            idempotency_key=idempotency_key
        )
        session.add(log)
        await session.commit()
        await session.refresh(shipment)
        return shipment

    @staticmethod
    async def receive_fbo(
        session: AsyncSession, shipment_id: int, idempotency_key: Optional[str] = None
    ) -> Shipment:
        """
        Фиксирует факт приёмки поставки FBO маркетплейсом
        Идемпотентно: повторные подтверждения не дублируют операцию
        """
        shipment = await session.get(Shipment, shipment_id)
        if not shipment or shipment.shipment_type != "FBO":
            raise BusinessLogicException("Поставка FBO не найдена")

        if shipment.status == "RECEIVED_BY_MP":
            return shipment

        if shipment.status != "SHIPPED_TO_MP":
            raise BusinessLogicException(f"Принять можно только поставку в пути (текущий статус: {shipment.status})")

        shipment.status = "RECEIVED_BY_MP"
        prod = await session.get(Product, shipment.product_id)
        wh = await session.get(Warehouse, shipment.warehouse_id)

        log = OperationLog(
            operation_type="FBO_RECEIVE",
            product_id=shipment.product_id,
            from_warehouse_id=shipment.warehouse_id,
            quantity=shipment.quantity,
            destination_desc="Принято маркетплейсом (FBO)",
            comment=f"Поставка FBO ({shipment.quantity} шт. {prod.sku}) принята маркетплейсом",
            idempotency_key=idempotency_key
        )
        session.add(log)
        await session.commit()
        await session.refresh(shipment)
        return shipment
