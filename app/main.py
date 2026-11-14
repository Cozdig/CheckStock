from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.api.endpoints import api_router
from app.services.exceptions import StockShortageException, BusinessLogicException
from app.services.seed_service import SeedService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создание таблиц при старте (если не созданы)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Автоматическая загрузка начальных данных по ТЗ, если база пустая
    async with AsyncSessionLocal() as session:
        await SeedService.seed_data(session)

    yield

    # Закрытие соединений
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Веб-прототип CheckStock: учёт остатков, перемещения между ФФ, отправки FBS/FBO",
    version="1.0.0",
    lifespan=lifespan
)

# Подключение API роутера
app.include_router(api_router)


# --- Обработчики исключений бизнес-логики ---
@app.exception_handler(StockShortageException)
async def stock_shortage_handler(request: Request, exc: StockShortageException):
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "STOCK_SHORTAGE",
            "message": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(BusinessLogicException)
async def business_logic_handler(request: Request, exc: BusinessLogicException):
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "BUSINESS_LOGIC_ERROR",
            "message": exc.message,
            "details": exc.details
        }
    )


# Базовый healthcheck
@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}
