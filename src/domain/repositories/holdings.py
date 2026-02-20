"""Holdings repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.holdings import HoldingsSnapshot

from .base import Repository


class HoldingsRepository(Repository[HoldingsSnapshot]):
    """Read/write interface for HoldingsSnapshot aggregates.

    Each snapshot is immutable after creation (no update or delete in the domain).
    get_latest returns the snapshot with the most recent snapshot_date.
    """

    async def get(self, id: UUID) -> HoldingsSnapshot | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, snapshot_id: UUID) -> HoldingsSnapshot | None:
        """Return the snapshot (with embedded positions), or None."""

    @abstractmethod
    async def get_latest(self) -> HoldingsSnapshot | None:
        """Return the snapshot with the most recent snapshot_date, or None if none exist."""

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> list[HoldingsSnapshot]:
        """Return a page of snapshots ordered by snapshot_date descending."""

    @abstractmethod
    async def create(self, entity: HoldingsSnapshot) -> HoldingsSnapshot:
        """Persist a snapshot and all its positions atomically."""
