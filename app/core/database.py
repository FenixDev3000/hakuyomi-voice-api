"""Configuración asíncrona de SQLAlchemy con PostgreSQL."""

import asyncio
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Inicializa las tablas en PostgreSQL al arrancar la aplicación."""
    # Compose v1 no espera al healthcheck de la base: reintenta hasta que acepte conexiones.
    for intento in range(1, 16):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception:
            if intento == 15:
                raise
            await asyncio.sleep(2)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia de sesión de base de datos para endpoints FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
