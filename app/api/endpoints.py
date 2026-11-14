from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.product import Product
from app.schemas.stock import (
    WarehouseCreate,
    WarehouseUpdate,
    WarehouseOut,
    ProductOut,
    ProductStockOverview,
    IncomeCreate,
    MovementCreate,
    MovementOut,
    FbsReserveCreate,
    FboShipCreate,
    ShipmentOut,
    OperationLogOut,
)
from app.services.stock_service import StockService
from app.services.warehouse_service import WarehouseService
from app.services.query_service import QueryService
from app.services.seed_service import SeedService

api_router = APIRouter(prefix="/api")


# --- Остатки (Главный экран) ---
@api_router.get("/overview", response_model=List[ProductStockOverview], summary="Сводка остатков по складам и товарам в пути")
async def get_overview(db: AsyncSession = Depends(get_db)):
    return await StockService.get_overview(db)


# --- Склады ---
@api_router.get("/warehouses", response_model=List[WarehouseOut], summary="Список складов ФФ")
async def get_warehouses(only_active: bool = False, db: AsyncSession = Depends(get_db)):
    return await WarehouseService.get_all(db, only_active=only_active)


@api_router.post("/warehouses", response_model=WarehouseOut, summary="Добавить новый склад ФФ")
async def create_warehouse(payload: WarehouseCreate, db: AsyncSession = Depends(get_db)):
    return await WarehouseService.create(db, payload.name)


@api_router.put("/warehouses/{warehouse_id}", response_model=WarehouseOut, summary="Переименовать склад")
async def rename_warehouse(warehouse_id: int, payload: WarehouseUpdate, db: AsyncSession = Depends(get_db)):
    return await WarehouseService.rename(db, warehouse_id, payload.name)


@api_router.delete("/warehouses/{warehouse_id}", summary="Удалить склад")
async def delete_warehouse(warehouse_id: int, db: AsyncSession = Depends(get_db)):
    return await WarehouseService.delete(db, warehouse_id)


# --- Товары ---
@api_router.get("/products", response_model=List[ProductOut], summary="Список всех товаров")
async def get_products(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Product).order_by(Product.id))
    return list(res.scalars().all())


# --- Операции: Приход ---
@api_router.post("/stock/income", summary="Оформить приход товара на склад")
async def add_income(payload: IncomeCreate, db: AsyncSession = Depends(get_db)):
    stock = await StockService.add_income(db, payload.warehouse_id, payload.product_id, payload.quantity)
    return {"status": "ok", "message": "Приход успешно проведен", "warehouse_id": payload.warehouse_id, "physical_qty": stock.physical_qty}


# --- Операции: Перемещение между ФФ ---
@api_router.get("/movements", response_model=List[MovementOut], summary="Список перемещений между ФФ")
async def get_movements(db: AsyncSession = Depends(get_db)):
    return await QueryService.get_movements(db)


@api_router.post("/movements", summary="Отправить перемещение между складами")
async def create_movement(payload: MovementCreate, db: AsyncSession = Depends(get_db)):
    movement = await StockService.create_movement(
        db, payload.from_warehouse_id, payload.to_warehouse_id, payload.product_id, payload.quantity, payload.idempotency_key
    )
    return {"status": "ok", "movement_id": movement.id, "movement_status": movement.status}


@api_router.post("/movements/{movement_id}/receive", summary="Принять перемещение на складе назначения")
async def receive_movement(movement_id: int, idempotency_key: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    movement = await StockService.receive_movement(db, movement_id, idempotency_key)
    return {"status": "ok", "movement_id": movement.id, "movement_status": movement.status}


# --- Операции: FBS (Резерв, Отправка клиенту, Отмена, Вручение) ---
@api_router.post("/shipments/fbs/reserve", summary="Зарезервировать товар под заказ FBS")
async def reserve_fbs(payload: FbsReserveCreate, db: AsyncSession = Depends(get_db)):
    shipment = await StockService.reserve_fbs(
        db, payload.warehouse_id, payload.product_id, payload.quantity, payload.idempotency_key
    )
    return {"status": "ok", "shipment_id": shipment.id, "shipment_status": shipment.status}


@api_router.post("/shipments/fbs/{shipment_id}/ship", summary="Отправить заказ FBS клиенту (списание со склада)")
async def ship_fbs(shipment_id: int, idempotency_key: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    shipment = await StockService.ship_fbs(db, shipment_id, idempotency_key)
    return {"status": "ok", "shipment_id": shipment.id, "shipment_status": shipment.status}


@api_router.post("/shipments/fbs/{shipment_id}/cancel", summary="Отменить резерв FBS")
async def cancel_fbs_reserve(shipment_id: int, db: AsyncSession = Depends(get_db)):
    shipment = await StockService.cancel_fbs_reserve(db, shipment_id)
    return {"status": "ok", "shipment_id": shipment.id, "shipment_status": shipment.status}


@api_router.post("/shipments/fbs/{shipment_id}/deliver", summary="Подтвердить доставку FBS клиенту")
async def deliver_fbs(shipment_id: int, db: AsyncSession = Depends(get_db)):
    shipment = await StockService.deliver_fbs(db, shipment_id)
    return {"status": "ok", "shipment_id": shipment.id, "shipment_status": shipment.status}


# --- Операции: FBO (Отгрузка на склад МП, Приёмка маркетплейсом) ---
@api_router.post("/shipments/fbo/ship", summary="Отгрузить партию FBO на маркетплейс (списание с ФФ, статус 'в пути')")
async def ship_fbo(payload: FboShipCreate, db: AsyncSession = Depends(get_db)):
    shipment = await StockService.ship_fbo(
        db, payload.warehouse_id, payload.product_id, payload.quantity, payload.destination, payload.idempotency_key
    )
    return {"status": "ok", "shipment_id": shipment.id, "shipment_status": shipment.status}


@api_router.post("/shipments/fbo/{shipment_id}/receive", summary="Приёмка партии FBO маркетплейсом")
async def receive_fbo(shipment_id: int, idempotency_key: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    shipment = await StockService.receive_fbo(db, shipment_id, idempotency_key)
    return {"status": "ok", "shipment_id": shipment.id, "shipment_status": shipment.status}


# --- Список отправок FBS / FBO ---
@api_router.get("/shipments", response_model=List[ShipmentOut], summary="Список всех отправок FBS/FBO")
async def get_shipments(shipment_type: Optional[str] = Query(None, description="Фильтр: FBS или FBO"), db: AsyncSession = Depends(get_db)):
    return await QueryService.get_shipments(db, shipment_type=shipment_type)


# --- История операций ---
@api_router.get("/logs", response_model=List[OperationLogOut], summary="История операций со складами и товарами")
async def get_logs(limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await QueryService.get_operation_logs(db, limit=limit)


# --- Сид стартовых данных ---
@api_router.post("/seed", summary="Загрузить тестовые данные из ТЗ (Север, Юг, Органайзер, Контейнер, Корзина)")
async def seed_data(db: AsyncSession = Depends(get_db)):
    return await SeedService.seed_data(db)
