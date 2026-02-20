"""Generic repository base interface.

Repository[T] is the root abstraction for all data-access interfaces in this
domain layer.  Concrete implementations live in src/infrastructure/persistence/
and are wired at the application boundary via dependency injection.

Design notes:
  - All methods are async to accommodate async database drivers (asyncpg / SQLAlchemy async).
  - T is the domain model type (never an ORM row or DTO).
  - list() accepts only limit/offset; domain-specific filters are declared
    on each specialised interface (Interface Segregation Principle).
  - update() and delete() are present on the base; specialised interfaces may
    leave them unsupported when the domain treats aggregates as append-only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Abstract CRUD interface for a domain aggregate or entity."""

    @abstractmethod
    async def get(self, id: UUID) -> T | None:
        """Return the entity with the given primary key, or None if not found."""

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> list[T]:
        """Return a page of entities ordered by creation time (newest first)."""

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Persist a new entity and return it (with any DB-generated fields populated)."""

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Persist changes to an existing entity and return the updated version."""

    @abstractmethod
    async def delete(self, id: UUID) -> None:
        """Remove the entity with the given primary key."""
