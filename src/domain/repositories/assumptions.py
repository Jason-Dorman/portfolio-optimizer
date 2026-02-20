"""Assumption set repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.assumptions import (
    AssetStats,
    AssumptionSet,
    CorrelationMatrix,
    CovarianceMatrix,
)

from .base import Repository


class AssumptionRepository(Repository[AssumptionSet]):
    """Read/write interface for AssumptionSet aggregates.

    Assumption sets are immutable after creation (estimation is always a new
    versioned snapshot).  create() saves the assumption set, per-asset stats,
    and covariance matrix atomically in a single transaction.

    Note: create() overrides the base signature with additional required
    parameters (stats and covariance) because all three must be persisted
    together — an assumption set without its μ and Σ is unusable.
    """

    async def get(self, id: UUID) -> AssumptionSet | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, assumption_id: UUID) -> AssumptionSet | None:
        """Return the assumption set, or None."""

    @abstractmethod
    async def list(
        self,
        universe_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssumptionSet]:
        """Return a page of assumption sets, optionally filtered by universe."""

    @abstractmethod
    async def create(  # type: ignore[override]
        self,
        assumption_set: AssumptionSet,
        stats: list[AssetStats],
        covariance: CovarianceMatrix,
    ) -> AssumptionSet:
        """Persist the assumption set with its per-asset stats and covariance matrix.

        All three are written atomically.  The returned AssumptionSet reflects
        any DB-generated fields (e.g. created_at normalised to UTC).
        """

    @abstractmethod
    async def get_covariance_matrix(self, assumption_id: UUID) -> CovarianceMatrix | None:
        """Return the full upper-triangle covariance matrix, or None."""

    @abstractmethod
    async def get_correlation_matrix(self, assumption_id: UUID) -> CorrelationMatrix | None:
        """Return the full upper-triangle correlation matrix, or None.

        Derived from covariance: corr(i,j) = cov(i,j) / (σ_i × σ_j).
        May be computed on-the-fly or cached — callers should not assume either.
        """
