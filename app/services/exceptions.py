from typing import Any, Dict, List, Optional


class BusinessLogicException(Exception):
    """Базовое исключение для ошибок бизнес-логики приложения"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class StockShortageException(BusinessLogicException):
    """
    Исключение, сигнализирующее о нехватке товара на конкретном складе,
    содержащее контекст наличия остатка на альтернативных складах сети
    """

    def __init__(
        self,
        message: str,
        product_id: int,
        sku: str,
        requested_qty: int,
        available_here: int,
        total_available: int,
        alternatives: List[Dict[str, Any]]
    ):
        super().__init__(message, {
            "product_id": product_id,
            "sku": sku,
            "requested_qty": requested_qty,
            "available_here": available_here,
            "total_available": total_available,
            "alternatives": alternatives
        })
        self.sku = sku
        self.requested_qty = requested_qty
        self.available_here = available_here
        self.total_available = total_available
        self.alternatives = alternatives
