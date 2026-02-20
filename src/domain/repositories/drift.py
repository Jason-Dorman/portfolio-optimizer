"""Drift repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.drift import DriftCheck, DriftPosition

from .base import Repository


class DriftRepository(Repository[DriftCheck]):
    """Read/write interface for DriftCheck aggregates.

    Drift checks are immutable after creation (append-only audit log).
    get_positions() provides direct access to position-level detail without
    loading the full aggregate — useful for position-level breach reporting.
    """

    async def get(self, id: UUID) -> DriftCheck | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, drift_id: UUID) -> DriftCheck | None:
        """Return the drift check with embedded positions, or None."""

    @abstractmethod
    async def create(self, entity: DriftCheck) -> DriftCheck:
        """Persist the drift check and all its positions atomically."""

    @abstractmethod
    async def get_positions(self, drift_id: UUID) -> list[DriftPosition]:
        """Return all per-asset drift positions for the given drift check."""
