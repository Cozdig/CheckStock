from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# --- Склады ---
class WarehouseBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Название склада")


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class WarehouseOut(WarehouseBase):
    id: int
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Товары ---
class ProductBase(BaseModel):
    sku: str = Field(..., min_length=2, max_length=50, description="Артикул")
    name: str = Field(..., min_length=2, max_length=150, description="Наименование товара")


class ProductCreate(ProductBase):
    pass


class ProductOut(ProductBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Остатки ---
class StockItemOut(BaseModel):
    warehouse_id: int
    warehouse_name: str
    warehouse_is_active: bool
    physical_qty: int
    reserved_fbs_qty: int
    available_qty: int


class ProductStockOverview(BaseModel):
    product_id: int
    sku: str
    product_name: str
    stocks_by_warehouse: List[StockItemOut]
    total_physical: int
    total_reserved_fbs: int
    total_available: int
    in_transit_between_wh: int
    in_transit_fbo: int
    in_transit_fbs: int


# --- Операции ---
class IncomeCreate(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: int = Field(..., gt=0, description="Количество для прихода (больше 0)")


class MovementCreate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    product_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = None


class MovementOut(BaseModel):
    id: int
    from_warehouse_id: int
    from_warehouse_name: str
    to_warehouse_id: int
    to_warehouse_name: str
    product_id: int
    sku: str
    product_name: str
    quantity: int
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FbsReserveCreate(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = None


class FboShipCreate(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: int = Field(..., gt=0)
    destination: Optional[str] = "Склад маркетплейса (FBO)"
    idempotency_key: Optional[str] = None


class ShipmentOut(BaseModel):
    id: int
    shipment_type: str
    warehouse_id: int
    warehouse_name: str
    product_id: int
    sku: str
    product_name: str
    quantity: int
    status: str
    destination: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OperationLogOut(BaseModel):
    id: int
    operation_type: str
    product_sku: str
    product_name: str
    from_warehouse_name: Optional[str] = None
    to_warehouse_name: Optional[str] = None
    destination_desc: Optional[str] = None
    quantity: int
    comment: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
