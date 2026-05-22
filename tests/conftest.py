import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base_class import Base
from app.db.session import get_db
from app.core.config import settings


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    # Create engine fresh for each test to avoid loop binding issues
    engine = create_async_engine(
        settings.POSTGRES_URI,
        pool_size=5,
        max_overflow=10,
        echo=False,
        future=True,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        settings.POSTGRES_URI,
        pool_size=2,
        max_overflow=5,
        echo=False,
        future=True,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
    await engine.dispose()
