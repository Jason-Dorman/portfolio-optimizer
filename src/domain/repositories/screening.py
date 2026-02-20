"""Screening repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.screening import ScreeningRun, ScreeningScore

from .base import Repository


class ScreeningRepository(Repository[ScreeningRun]):
    """Read/write interface for ScreeningRun aggregates.

    Screening runs are immutable after creation.  create() saves the run and
    all its scores atomically.  get_scores() supports paginated access to the
    full candidate score list (useful when the candidate pool is large).
    """

    async def get(self, id: UUID) -> ScreeningRun | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, screening_id: UUID) -> ScreeningRun | None:
        """Return the screening run with embedded scores, or None."""

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> list[ScreeningRun]:
        """Return a page of screening runs ordered by creation time descending."""

    @abstractmethod
    async def create(self, entity: ScreeningRun) -> ScreeningRun:
        """Persist the screening run and all its candidate scores atomically."""

    @abstractmethod
    async def get_scores(
        self,
        screening_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScreeningScore]:
        """Return a paginated, rank-ordered list of scores for one screening run."""
