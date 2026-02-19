"""Unit tests for src/infrastructure/database.py.

Tests cover Settings defaults, env var override, and object types.
No database connection is required.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.infrastructure.database import AsyncSessionLocal, Base, Settings, engine


def test_settings_default_url_uses_asyncpg():
    assert "postgresql+asyncpg" in Settings().database_url


def test_settings_default_url_targets_localhost():
    assert "localhost" in Settings().database_url


def test_settings_reads_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@myhost/mydb")
    assert Settings().database_url == "postgresql+asyncpg://u:p@myhost/mydb"


def test_base_is_declarative_base():
    assert issubclass(Base, DeclarativeBase)


def test_engine_is_async():
    assert isinstance(engine, AsyncEngine)


def test_session_factory_produces_async_sessions():
    assert isinstance(AsyncSessionLocal, async_sessionmaker)
    assert AsyncSessionLocal.class_ is AsyncSession
