"""Async database engine and session factory shared across modules.

Usage:
    from modules.shared.db import get_session

    async with get_session() as session:
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.config import get_settings
from modules.shared.db.models import (
    Base,
    Document,
    DocumentType,
    ParseJob,
    ParseJobStatus,
    ParseSection,
    Schema,
)

__all__ = [
    "Base",
    "Document",
    "DocumentType",
    "ParseJob",
    "ParseJobStatus",
    "ParseSection",
    "Schema",
    "get_engine",
    "get_sessionmaker",
    "get_session",
]


@lru_cache
def get_engine() -> AsyncEngine:
    """Lazily create the shared async engine from runtime settings."""
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(), expire_on_commit=False, class_=AsyncSession
    )


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session, committing on success and rolling back on error."""
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
