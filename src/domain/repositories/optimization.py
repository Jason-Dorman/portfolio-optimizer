"""Optimization repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.enums import OptimizationStatus
from src.domain.models.optimization import OptimizationRun, PortfolioWeight

from .base import Repository


class OptimizationRepository(Repository[OptimizationRun]):
    """Read/write interface for OptimizationRun aggregates.

    Optimization runs are immutable after creation.  create() persists the run,
    its result (if successful), and all portfolio weights atomically.

    get_weights() provides direct access to the weights without loading the
    full run aggregate — useful for risk decomposition queries.

    get_latest_for_universe() traverses assumption_sets → optimization_runs to
    find the most recent successful run for a given universe (used by drift
    detection and turnover-constraint fallback logic).
    """

    async def get(self, id: UUID) -> OptimizationRun | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, run_id: UUID) -> OptimizationRun | None:
        """Return the run with embedded weights and result, or None."""

    @abstractmethod
    async def list(
        self,
        assumption_id: UUID | None = None,
        status: OptimizationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OptimizationRun]:
        """Return a page of runs, optionally filtered by assumption set or status."""

    @abstractmethod
    async def create(self, entity: OptimizationRun) -> OptimizationRun:
        """Persist the run, its result, and all portfolio weights atomically."""

    @abstractmethod
    async def get_weights(self, run_id: UUID) -> list[PortfolioWeight]:
        """Return portfolio weights for the run (empty list if run is INFEASIBLE/ERROR)."""

    @abstractmethod
    async def get_latest_for_universe(self, universe_id: UUID) -> OptimizationRun | None:
        """Return the most recent successful run for the given universe, or None.

        Resolves via: universe → assumption_sets → optimization_runs (status=SUCCESS).
        Used as the turnover-constraint fallback when no reference snapshot is provided.
        """
