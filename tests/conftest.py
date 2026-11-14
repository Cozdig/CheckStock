import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.testclient import TestClient

from app.core.database import Base, get_db
from app.main import app
from app.services.seed_service import SeedService

TEST_DB_FILE = "./test_checkstock.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def setup_test_db():
    async def init():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        async with TestSessionLocal() as session:
            await SeedService.seed_data(session)

    asyncio.run(init())

    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
