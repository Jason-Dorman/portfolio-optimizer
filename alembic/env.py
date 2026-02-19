"""Alembic env.py — configured for async SQLAlchemy (asyncpg)."""

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Alembic Config object — access to alembic.ini values.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base, settings, and register all ORM models so Alembic can detect schema changes.
from src.infrastructure.database import Base, settings  # noqa: E402
import src.infrastructure.persistence.models  # noqa: E402, F401

target_metadata = Base.metadata

# settings already loads DATABASE_URL from the .env file via pydantic-settings.
DATABASE_URL = settings.database_url


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live DB using an async engine."""
    connectable = create_async_engine(DATABASE_URL, echo=False)  # type: ignore[arg-type]

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
