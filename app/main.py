import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.api.endpoints import api_router
from app.services.exceptions import StockShortageException, BusinessLogicException
from app.services.seed_service import SeedService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await SeedService.seed_data(session)

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Веб-прототип CheckStock: учёт остатков, перемещения между ФФ, отправки FBS/FBO",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router)


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


@app.get("/", response_class=HTMLResponse, summary="Главная страница панели управления")
async def get_index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"project_name": settings.PROJECT_NAME}
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}
